import asyncio
import uuid
from datetime import timedelta
from typing import Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.compute import ComputeWithPlacementGroupSupport
from dstack._internal.core.errors import PlacementGroupInUseError
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    UpdateMap,
    Worker,
    get_processed_update_map,
    get_unlock_update_map,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    PlacementGroupModel,
    ProjectModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.placement import placement_group_model_to_placement_group
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class PlacementGroupPipeline(Pipeline[PipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=15),
        lock_timeout: timedelta = timedelta(seconds=30),
        heartbeat_trigger: timedelta = timedelta(seconds=15),
    ) -> None:
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[PipelineItem](
            model_type=PlacementGroupModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = PlacementGroupFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            PlacementGroupWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return PlacementGroupModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[PipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[PipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["PlacementGroupWorker"]:
        return self.__workers


class PlacementGroupFetcher(Fetcher[PipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[PipelineItem],
        queue_check_delay: float = 1.0,
    ) -> None:
        super().__init__(
            queue=queue,
            queue_desired_minsize=queue_desired_minsize,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeater=heartbeater,
            queue_check_delay=queue_check_delay,
        )

    async def fetch(self, limit: int) -> list[PipelineItem]:
        placement_group_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            PlacementGroupModel.__tablename__
        )
        async with placement_group_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(PlacementGroupModel)
                    .where(
                        PlacementGroupModel.fleet_deleted == True,
                        PlacementGroupModel.deleted == False,
                        PlacementGroupModel.last_processed_at
                        <= now - self._min_processing_interval,
                        or_(
                            PlacementGroupModel.lock_expires_at.is_(None),
                            PlacementGroupModel.lock_expires_at < now,
                        ),
                        or_(
                            PlacementGroupModel.lock_owner.is_(None),
                            PlacementGroupModel.lock_owner == PlacementGroupPipeline.__name__,
                        ),
                    )
                    .order_by(PlacementGroupModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True)
                    .options(
                        load_only(
                            PlacementGroupModel.id,
                            PlacementGroupModel.lock_token,
                            PlacementGroupModel.lock_expires_at,
                        )
                    )
                )
                placement_group_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for placement_group_model in placement_group_models:
                    prev_lock_expired = placement_group_model.lock_expires_at is not None
                    placement_group_model.lock_expires_at = lock_expires_at
                    placement_group_model.lock_token = lock_token
                    placement_group_model.lock_owner = PlacementGroupPipeline.__name__
                    items.append(
                        PipelineItem(
                            __tablename__=PlacementGroupModel.__tablename__,
                            id=placement_group_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                        )
                    )
                await session.commit()
        return items


class PlacementGroupWorker(Worker[PipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        heartbeater: Heartbeater[PipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    async def process(self, item: PipelineItem):
        async with get_session_ctx() as session:
            res = await session.execute(
                select(PlacementGroupModel)
                .where(
                    PlacementGroupModel.id == item.id,
                    PlacementGroupModel.lock_token == item.lock_token,
                )
                .options(joinedload(PlacementGroupModel.project).joinedload(ProjectModel.backends))
            )
            placement_group_model = res.unique().scalar_one_or_none()
            if placement_group_model is None:
                logger.warning(
                    "Failed to process %s item %s: lock_token mismatch."
                    " The item is expected to be processed and updated on another fetch iteration.",
                    item.__tablename__,
                    item.id,
                )
                return

        update_map = await _delete_placement_group(placement_group_model)
        if update_map:
            logger.info("Deleted placement group %s", placement_group_model.name)
        else:
            update_map = get_processed_update_map()

        update_map |= get_unlock_update_map()

        async with get_session_ctx() as session:
            res = await session.execute(
                update(PlacementGroupModel)
                .where(
                    PlacementGroupModel.id == placement_group_model.id,
                    PlacementGroupModel.lock_token == placement_group_model.lock_token,
                )
                .values(**update_map)
                .returning(PlacementGroupModel.id)
            )
            updated_ids = list(res.scalars().all())
            if len(updated_ids) == 0:
                logger.warning(
                    "Failed to update %s item %s after processing: lock_token changed."
                    " The item is expected to be processed and updated on another fetch iteration.",
                    item.__tablename__,
                    item.id,
                )


async def _delete_placement_group(placement_group_model: PlacementGroupModel) -> UpdateMap:
    placement_group = placement_group_model_to_placement_group(placement_group_model)
    if placement_group.provisioning_data is None:
        logger.error(
            "Failed to delete placement group %s. provisioning_data is None.", placement_group.name
        )
        return _get_deleted_update_map()
    backend = await backends_services.get_project_backend_by_type(
        project=placement_group_model.project,
        backend_type=placement_group.provisioning_data.backend,
    )
    if backend is None:
        # TODO: Retry deletion
        logger.error(
            "Failed to delete placement group %s. Backend not available. Please delete it manually.",
            placement_group.name,
        )
        return _get_deleted_update_map()
    compute = backend.compute()
    assert isinstance(compute, ComputeWithPlacementGroupSupport)
    try:
        await run_async(compute.delete_placement_group, placement_group)
    except PlacementGroupInUseError:
        logger.info(
            "Placement group %s is still in use. Skipping deletion for now.", placement_group.name
        )
        return {}
    except Exception:
        # TODO: Retry deletion
        logger.exception(
            "Got exception when deleting placement group %s. Please delete it manually.",
            placement_group.name,
        )
        return _get_deleted_update_map()

    return _get_deleted_update_map()


def _get_deleted_update_map() -> UpdateMap:
    now = get_current_datetime()
    return {
        "last_processed_at": now,
        "deleted": True,
        "deleted_at": now,
    }
