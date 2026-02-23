import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.errors import BackendError, BackendNotAvailable
from dstack._internal.core.models.volumes import VolumeStatus
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
    FleetModel,
    InstanceModel,
    ProjectModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.volumes import (
    emit_volume_status_change_event,
    volume_model_to_volume,
)
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VolumePipelineItem(PipelineItem):
    status: VolumeStatus


class VolumePipeline(Pipeline[VolumePipelineItem]):
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
        self.__heartbeater = Heartbeater[VolumePipelineItem](
            model_type=VolumeModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = VolumeFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            VolumeWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return VolumeModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[VolumePipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[VolumePipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["VolumeWorker"]:
        return self.__workers


class VolumeFetcher(Fetcher[VolumePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[VolumePipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[VolumePipelineItem],
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

    async def fetch(self, limit: int) -> list[VolumePipelineItem]:
        volume_lock, _ = get_locker(get_db().dialect_name).get_lockset(VolumeModel.__tablename__)
        async with volume_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(VolumeModel)
                    .where(
                        or_(
                            VolumeModel.status.in_([VolumeStatus.SUBMITTED]),
                            # VolumeModel.to_be_deleted == True,
                        ),
                        VolumeModel.deleted == False,
                        or_(
                            VolumeModel.last_processed_at <= now - self._min_processing_interval,
                            VolumeModel.last_processed_at == VolumeModel.created_at,
                        ),
                        or_(
                            VolumeModel.lock_expires_at.is_(None),
                            VolumeModel.lock_expires_at < now,
                        ),
                        or_(
                            VolumeModel.lock_owner.is_(None),
                            VolumeModel.lock_owner == VolumePipeline.__name__,
                        ),
                    )
                    .order_by(VolumeModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True)
                    .options(
                        load_only(
                            VolumeModel.id,
                            VolumeModel.lock_token,
                            VolumeModel.lock_expires_at,
                            VolumeModel.status,
                        )
                    )
                )
                volume_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for volume_model in volume_models:
                    prev_lock_expired = volume_model.lock_expires_at is not None
                    volume_model.lock_expires_at = lock_expires_at
                    volume_model.lock_token = lock_token
                    volume_model.lock_owner = VolumePipeline.__name__
                    items.append(
                        VolumePipelineItem(
                            __tablename__=VolumeModel.__tablename__,
                            id=volume_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=volume_model.status,
                        )
                    )
                await session.commit()
        return items


class VolumeWorker(Worker[VolumePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[VolumePipelineItem],
        heartbeater: Heartbeater[VolumePipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    async def process(self, item: VolumePipelineItem):
        await _process_submitted_item(item)


async def _process_submitted_item(item: VolumePipelineItem):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(VolumeModel)
            .where(
                VolumeModel.id == item.id,
                VolumeModel.lock_token == item.lock_token,
            )
            .options(joinedload(VolumeModel.project).joinedload(ProjectModel.backends))
            .options(joinedload(VolumeModel.user))
            .options(
                joinedload(VolumeModel.attachments)
                .joinedload(VolumeAttachmentModel.instance)
                .joinedload(InstanceModel.fleet)
                .load_only(FleetModel.name)
            )
        )
        volume_model = res.unique().scalar_one_or_none()
        if volume_model is None:
            logger.warning(
                "Failed to process %s item %s: lock_token mismatch."
                " The item is expected to be processed and updated on another fetch iteration.",
                item.__tablename__,
                item.id,
            )
            return

    result = await _process_submitted_volume(volume_model)
    update_map = result.update_map | get_processed_update_map() | get_unlock_update_map()
    async with get_session_ctx() as session:
        res = await session.execute(
            update(VolumeModel)
            .where(
                VolumeModel.id == volume_model.id,
                VolumeModel.lock_token == volume_model.lock_token,
            )
            .values(**update_map)
            .returning(VolumeModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            logger.warning(
                "Failed to update %s item %s after processing: lock_token changed."
                " The item is expected to be processed and updated on another fetch iteration.",
                item.__tablename__,
                item.id,
            )
            # TODO: Clean up volume.
            return
        emit_volume_status_change_event(
            session=session,
            volume_model=volume_model,
            old_status=volume_model.status,
            new_status=update_map.get("status", volume_model.status),
            status_message=update_map.get("status_message", volume_model.status_message),
        )


@dataclass
class _SubmittedResult:
    update_map: UpdateMap = field(default_factory=dict)


async def _process_submitted_volume(volume_model: VolumeModel) -> _SubmittedResult:
    volume = volume_model_to_volume(volume_model)
    try:
        backend = await backends_services.get_project_backend_by_type_or_error(
            project=volume_model.project,
            backend_type=volume.configuration.backend,
            overrides=True,
        )
    except BackendNotAvailable:
        logger.error(
            "Failed to process volume %s. Backend %s not available.",
            volume.name,
            volume.configuration.backend.value,
        )
        return _SubmittedResult(
            update_map={
                "status": VolumeStatus.FAILED,
                "status_message": "Backend not available",
            }
        )

    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)
    try:
        if volume.configuration.volume_id is not None:
            logger.info("Registering external volume %s", volume_model.name)
            vpd = await run_async(
                compute.register_volume,
                volume=volume,
            )
        else:
            logger.info("Provisioning new volume %s", volume_model.name)
            vpd = await run_async(
                compute.create_volume,
                volume=volume,
            )
    except BackendError as e:
        logger.info("Failed to create volume %s: %s", volume_model.name, repr(e))
        status_message = f"Backend error: {repr(e)}"
        if len(e.args) > 0:
            status_message = str(e.args[0])
        return _SubmittedResult(
            update_map={
                "status": VolumeStatus.FAILED,
                "status_message": status_message,
            }
        )
    except Exception as e:
        logger.exception("Got exception when creating volume %s", volume_model.name)
        return _SubmittedResult(
            update_map={
                "status": VolumeStatus.FAILED,
                "status_message": f"Unexpected error: {repr(e)}",
            }
        )

    logger.info("Added new volume %s", volume_model.name)
    # Provisioned volumes marked as active since they become available almost immediately in AWS
    # TODO: Consider checking volume state
    return _SubmittedResult(
        update_map={
            "status": VolumeStatus.ACTIVE,
            "volume_provisioning_data": vpd.json(),
        }
    )
