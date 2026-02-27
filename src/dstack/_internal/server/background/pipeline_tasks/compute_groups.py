import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence, TypedDict

from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.compute import ComputeWithGroupProvisioningSupport
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.compute_groups import ComputeGroupStatus
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    NOW_PLACEHOLDER,
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
    UpdateMapDateTime,
    Worker,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import ComputeGroupModel, InstanceModel, ProjectModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.compute_groups import compute_group_model_to_compute_group
from dstack._internal.server.services.instances import emit_instance_status_change_event
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

TERMINATION_RETRY_TIMEOUT = timedelta(seconds=60)
TERMINATION_RETRY_MAX_DURATION = timedelta(minutes=15)


class ComputeGroupPipeline(Pipeline[PipelineItem]):
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
            model_type=ComputeGroupModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = ComputeGroupFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            ComputeGroupWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return ComputeGroupModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[PipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[PipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["ComputeGroupWorker"]:
        return self.__workers


class ComputeGroupFetcher(Fetcher[PipelineItem]):
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

    @sentry_utils.instrument_named_task("pipeline_tasks.ComputeGroupFetcher.fetch")
    async def fetch(self, limit: int) -> list[PipelineItem]:
        compute_group_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            ComputeGroupModel.__tablename__
        )
        async with compute_group_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(ComputeGroupModel)
                    .where(
                        ComputeGroupModel.status.not_in(ComputeGroupStatus.finished_statuses()),
                        ComputeGroupModel.last_processed_at <= now - self._min_processing_interval,
                        or_(
                            ComputeGroupModel.lock_expires_at.is_(None),
                            ComputeGroupModel.lock_expires_at < now,
                        ),
                        or_(
                            ComputeGroupModel.lock_owner.is_(None),
                            ComputeGroupModel.lock_owner == ComputeGroupPipeline.__name__,
                        ),
                    )
                    .order_by(ComputeGroupModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=ComputeGroupModel)
                    .options(
                        load_only(
                            ComputeGroupModel.id,
                            ComputeGroupModel.lock_token,
                            ComputeGroupModel.lock_expires_at,
                        )
                    )
                )
                compute_group_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for compute_group_model in compute_group_models:
                    prev_lock_expired = compute_group_model.lock_expires_at is not None
                    compute_group_model.lock_expires_at = lock_expires_at
                    compute_group_model.lock_token = lock_token
                    compute_group_model.lock_owner = ComputeGroupPipeline.__name__
                    items.append(
                        PipelineItem(
                            __tablename__=ComputeGroupModel.__tablename__,
                            id=compute_group_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                        )
                    )
                await session.commit()
        return items


class ComputeGroupWorker(Worker[PipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        heartbeater: Heartbeater[PipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.ComputeGroupWorker.process")
    async def process(self, item: PipelineItem):
        async with get_session_ctx() as session:
            res = await session.execute(
                select(ComputeGroupModel)
                .where(
                    ComputeGroupModel.id == item.id,
                    ComputeGroupModel.lock_token == item.lock_token,
                )
                # Terminating instances belonging to a compute group are locked implicitly by locking the compute group.
                .options(
                    joinedload(ComputeGroupModel.instances),
                    joinedload(ComputeGroupModel.project).joinedload(ProjectModel.backends),
                )
            )
            compute_group_model = res.unique().scalar_one_or_none()
            if compute_group_model is None:
                logger.warning(
                    "Failed to process %s item %s: lock_token mismatch."
                    " The item is expected to be processed and updated on another fetch iteration.",
                    item.__tablename__,
                    item.id,
                )
                return

        result = _TerminateResult()
        # TODO: Fetch only compute groups with all instances terminating.
        if all(i.status == InstanceStatus.TERMINATING for i in compute_group_model.instances):
            result = await _terminate_compute_group(compute_group_model)
        set_processed_update_map_fields(result.compute_group_update_map)
        if result.instances_update_map:
            set_processed_update_map_fields(result.instances_update_map)
        set_unlock_update_map_fields(result.compute_group_update_map)
        if result.compute_group_update_map.get("deleted", False):
            logger.info("Terminated compute group %s", compute_group_model.id)

        async with get_session_ctx() as session:
            now = get_current_datetime()
            resolve_now_placeholders(result.compute_group_update_map, now=now)
            resolve_now_placeholders(result.instances_update_map, now=now)
            res = await session.execute(
                update(ComputeGroupModel)
                .where(
                    ComputeGroupModel.id == compute_group_model.id,
                    ComputeGroupModel.lock_token == compute_group_model.lock_token,
                )
                .values(**result.compute_group_update_map)
                .returning(ComputeGroupModel.id)
            )
            updated_ids = list(res.scalars().all())
            if len(updated_ids) == 0:
                logger.warning(
                    "Failed to update %s item %s after processing: lock_token changed."
                    " The item is expected to be processed and updated on another fetch iteration.",
                    item.__tablename__,
                    item.id,
                )
                return
            if not result.instances_update_map:
                return
            instances_ids = [i.id for i in compute_group_model.instances]
            res = await session.execute(
                update(InstanceModel)
                .where(InstanceModel.id.in_(instances_ids))
                .values(**result.instances_update_map)
            )
            for instance_model in compute_group_model.instances:
                emit_instance_status_change_event(
                    session=session,
                    instance_model=instance_model,
                    old_status=instance_model.status,
                    new_status=InstanceStatus.TERMINATED,
                )


class _ComputeGroupUpdateMap(ItemUpdateMap, total=False):
    status: ComputeGroupStatus
    deleted: bool
    deleted_at: UpdateMapDateTime
    first_termination_retry_at: UpdateMapDateTime
    last_termination_retry_at: UpdateMapDateTime


class _InstanceBulkUpdateMap(TypedDict, total=False):
    last_processed_at: UpdateMapDateTime
    deleted: bool
    deleted_at: UpdateMapDateTime
    finished_at: UpdateMapDateTime
    status: InstanceStatus


@dataclass
class _TerminateResult:
    compute_group_update_map: _ComputeGroupUpdateMap = field(
        default_factory=_ComputeGroupUpdateMap
    )
    instances_update_map: _InstanceBulkUpdateMap = field(default_factory=_InstanceBulkUpdateMap)


async def _terminate_compute_group(compute_group_model: ComputeGroupModel) -> _TerminateResult:
    result = _TerminateResult()
    if (
        compute_group_model.last_termination_retry_at is not None
        and _next_termination_retry_at(compute_group_model.last_termination_retry_at)
        > get_current_datetime()
    ):
        return result
    compute_group = compute_group_model_to_compute_group(compute_group_model)
    cgpd = compute_group.provisioning_data
    backend = await backends_services.get_project_backend_by_type(
        project=compute_group_model.project,
        backend_type=cgpd.backend,
    )
    if backend is None:
        logger.error(
            "Failed to terminate compute group %s. Backend %s not available."
            " Please terminate it manually to avoid unexpected charges.",
            compute_group.name,
            cgpd.backend,
        )
        return _get_terminated_result()
    logger.debug("Terminating compute group %s", compute_group.name)
    compute = backend.compute()
    assert isinstance(compute, ComputeWithGroupProvisioningSupport)
    try:
        await run_async(
            compute.terminate_compute_group,
            compute_group,
        )
    except Exception as e:
        retry_at = get_current_datetime()
        first_termination_retry_at = compute_group_model.first_termination_retry_at
        if compute_group_model.first_termination_retry_at is None:
            result.compute_group_update_map["first_termination_retry_at"] = NOW_PLACEHOLDER
            first_termination_retry_at = retry_at
        assert first_termination_retry_at is not None
        result.compute_group_update_map["last_termination_retry_at"] = NOW_PLACEHOLDER
        if _next_termination_retry_at(retry_at) < _get_termination_deadline(
            first_termination_retry_at
        ):
            logger.warning(
                "Failed to terminate compute group %s. Will retry. Error: %r",
                compute_group.name,
                e,
                exc_info=not isinstance(e, BackendError),
            )
            return result
        logger.error(
            "Failed all attempts to terminate compute group %s."
            " Please terminate it manually to avoid unexpected charges."
            " Error: %r",
            compute_group.name,
            e,
            exc_info=not isinstance(e, BackendError),
        )
    terminated_result = _get_terminated_result()
    compute_group_update_map = _ComputeGroupUpdateMap()
    compute_group_update_map.update(result.compute_group_update_map)
    compute_group_update_map.update(terminated_result.compute_group_update_map)
    instances_update_map = _InstanceBulkUpdateMap()
    instances_update_map.update(result.instances_update_map)
    instances_update_map.update(terminated_result.instances_update_map)
    return _TerminateResult(
        compute_group_update_map=compute_group_update_map,
        instances_update_map=instances_update_map,
    )


def _next_termination_retry_at(last_termination_retry_at: datetime) -> datetime:
    return last_termination_retry_at + TERMINATION_RETRY_TIMEOUT


def _get_termination_deadline(first_termination_retry_at: datetime) -> datetime:
    return first_termination_retry_at + TERMINATION_RETRY_MAX_DURATION


def _get_terminated_result() -> _TerminateResult:
    return _TerminateResult(
        compute_group_update_map={
            "deleted": True,
            "deleted_at": NOW_PLACEHOLDER,
            "status": ComputeGroupStatus.TERMINATED,
        },
        instances_update_map={
            "deleted": True,
            "deleted_at": NOW_PLACEHOLDER,
            "finished_at": NOW_PLACEHOLDER,
            "status": InstanceStatus.TERMINATED,
        },
    )
