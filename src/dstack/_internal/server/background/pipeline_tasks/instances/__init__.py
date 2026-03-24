import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy import and_, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.background.pipeline_tasks.instances.check import (
    check_instance,
    process_idle_timeout,
)
from dstack._internal.server.background.pipeline_tasks.instances.cloud_provisioning import (
    create_cloud_instance,
)
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    ProcessResult,
)
from dstack._internal.server.background.pipeline_tasks.instances.ssh_deploy import (
    add_ssh_instance,
)
from dstack._internal.server.background.pipeline_tasks.instances.termination import (
    terminate_instance,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceHealthCheckModel,
    InstanceModel,
    JobModel,
    ProjectModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.instances import (
    emit_instance_status_change_event,
    is_ssh_instance,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.placement import (
    schedule_fleet_placement_groups_deletion,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InstancePipelineItem(PipelineItem):
    status: InstanceStatus


class InstancePipeline(Pipeline[InstancePipelineItem]):
    def __init__(
        self,
        workers_num: int = 20,
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
        self.__heartbeater = Heartbeater[InstancePipelineItem](
            model_type=InstanceModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = InstanceFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            InstanceWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return InstanceModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[InstancePipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[InstancePipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["InstanceWorker"]:
        return self.__workers


class InstanceFetcher(Fetcher[InstancePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[InstancePipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[InstancePipelineItem],
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

    @sentry_utils.instrument_named_task("pipeline_tasks.InstanceFetcher.fetch")
    async def fetch(self, limit: int) -> list[InstancePipelineItem]:
        instance_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            InstanceModel.__tablename__
        )
        async with instance_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(InstanceModel)
                    .join(InstanceModel.fleet, isouter=True)
                    .where(
                        InstanceModel.status.in_(
                            [
                                InstanceStatus.PENDING,
                                InstanceStatus.PROVISIONING,
                                InstanceStatus.BUSY,
                                InstanceStatus.IDLE,
                                InstanceStatus.TERMINATING,
                            ]
                        ),
                        not_(
                            and_(
                                InstanceModel.status == InstanceStatus.TERMINATING,
                                InstanceModel.compute_group_id.is_not(None),
                            )
                        ),
                        InstanceModel.deleted == False,
                        or_(
                            # Do not try to lock instances if the fleet is waiting for the lock.
                            InstanceModel.fleet_id.is_(None),
                            FleetModel.lock_owner.is_(None),
                        ),
                        or_(
                            InstanceModel.last_processed_at <= now - self._min_processing_interval,
                            InstanceModel.last_processed_at == InstanceModel.created_at,
                        ),
                        or_(
                            InstanceModel.lock_expires_at.is_(None),
                            InstanceModel.lock_expires_at < now,
                        ),
                        or_(
                            InstanceModel.lock_owner.is_(None),
                            InstanceModel.lock_owner == InstancePipeline.__name__,
                        ),
                    )
                    .order_by(InstanceModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=InstanceModel)
                    .options(
                        load_only(
                            InstanceModel.id,
                            InstanceModel.lock_token,
                            InstanceModel.lock_expires_at,
                            InstanceModel.status,
                        )
                    )
                )
                instance_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for instance_model in instance_models:
                    prev_lock_expired = instance_model.lock_expires_at is not None
                    instance_model.lock_expires_at = lock_expires_at
                    instance_model.lock_token = lock_token
                    instance_model.lock_owner = InstancePipeline.__name__
                    items.append(
                        InstancePipelineItem(
                            __tablename__=InstanceModel.__tablename__,
                            id=instance_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=instance_model.status,
                        )
                    )
                await session.commit()
        return items


class InstanceWorker(Worker[InstancePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[InstancePipelineItem],
        heartbeater: Heartbeater[InstancePipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.InstanceWorker.process")
    async def process(self, item: InstancePipelineItem):
        process_context: Optional[_ProcessContext] = None
        if item.status == InstanceStatus.PENDING:
            process_context = await _process_pending_item(item)
        elif item.status == InstanceStatus.PROVISIONING:
            process_context = await _process_provisioning_item(item)
        elif item.status == InstanceStatus.IDLE:
            process_context = await _process_idle_item(item)
        elif item.status == InstanceStatus.BUSY:
            process_context = await _process_busy_item(item)
        elif item.status == InstanceStatus.TERMINATING:
            process_context = await _process_terminating_item(item)
        if process_context is None:
            return

        # Keep apply centralized here because every instance path returns the same
        # `ProcessResult` shape for one primary model, with only a small set of
        # optional side effects such as health checks or placement-group scheduling.
        await _apply_process_result(
            item=item,
            instance_model=process_context.instance_model,
            result=process_context.result,
        )


@dataclass
class _ProcessContext:
    instance_model: InstanceModel
    result: ProcessResult


async def _process_pending_item(item: InstancePipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_pending_or_terminating(
            session=session,
            item=item,
        )
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    if is_ssh_instance(instance_model):
        result = await add_ssh_instance(instance_model)
    else:
        result = await create_cloud_instance(instance_model)
    return _ProcessContext(instance_model=instance_model, result=result)


async def _process_provisioning_item(item: InstancePipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_check(session=session, item=item)
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    result = await check_instance(instance_model)
    return _ProcessContext(instance_model=instance_model, result=result)


async def _process_idle_item(item: InstancePipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_idle(session=session, item=item)
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
        idle_result = await process_idle_timeout(
            session=session,
            instance_model=instance_model,
        )
        if idle_result is not None:
            return _ProcessContext(instance_model=instance_model, result=idle_result)
    result = await check_instance(instance_model)
    return _ProcessContext(instance_model=instance_model, result=result)


async def _process_busy_item(item: InstancePipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_check(session=session, item=item)
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    result = await check_instance(instance_model)
    return _ProcessContext(instance_model=instance_model, result=result)


async def _process_terminating_item(item: InstancePipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_pending_or_terminating(
            session=session,
            item=item,
        )
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    result = await terminate_instance(instance_model)
    return _ProcessContext(instance_model=instance_model, result=result)


async def _refetch_locked_instance_for_pending_or_terminating(
    session: AsyncSession, item: InstancePipelineItem
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == item.id,
            InstanceModel.lock_token == item.lock_token,
        )
        .options(joinedload(InstanceModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
        .options(joinedload(InstanceModel.fleet))
    )
    return res.unique().scalar_one_or_none()


async def _refetch_locked_instance_for_idle(
    session: AsyncSession, item: InstancePipelineItem
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == item.id,
            InstanceModel.lock_token == item.lock_token,
        )
        .options(joinedload(InstanceModel.project))
        .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
        .options(joinedload(InstanceModel.fleet))
    )
    return res.unique().scalar_one_or_none()


async def _refetch_locked_instance_for_check(
    session: AsyncSession, item: InstancePipelineItem
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == item.id,
            InstanceModel.lock_token == item.lock_token,
        )
        .options(
            joinedload(InstanceModel.project).load_only(
                ProjectModel.id,
                ProjectModel.ssh_public_key,
                ProjectModel.ssh_private_key,
            )
        )
        .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
    )
    return res.unique().scalar_one_or_none()


async def _apply_process_result(
    item: InstancePipelineItem,
    instance_model: InstanceModel,
    result: ProcessResult,
) -> None:
    set_processed_update_map_fields(result.instance_update_map)
    set_unlock_update_map_fields(result.instance_update_map)

    async with get_session_ctx() as session:
        if result.health_check_create is not None:
            session.add(InstanceHealthCheckModel(**result.health_check_create))
        if result.new_placement_group_models:
            session.add_all(result.new_placement_group_models)
        if result.health_check_create is not None or result.new_placement_group_models:
            await session.flush()

        now = get_current_datetime()
        resolve_now_placeholders(result.instance_update_map, now=now)

        res = await session.execute(
            update(InstanceModel)
            .where(
                InstanceModel.id == item.id,
                InstanceModel.lock_token == item.lock_token,
            )
            .values(**result.instance_update_map)
            .returning(InstanceModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            await session.rollback()
            return

        if result.schedule_pg_deletion_fleet_id is not None:
            await schedule_fleet_placement_groups_deletion(
                session=session,
                fleet_id=result.schedule_pg_deletion_fleet_id,
                except_placement_group_ids=(
                    ()
                    if result.schedule_pg_deletion_except_id is None
                    else (result.schedule_pg_deletion_except_id,)
                ),
            )

        emit_instance_status_change_event(
            session=session,
            instance_model=instance_model,
            old_status=instance_model.status,
            new_status=result.instance_update_map.get("status", instance_model.status),
            termination_reason=result.instance_update_map.get(
                "termination_reason", instance_model.termination_reason
            ),
            termination_reason_message=result.instance_update_map.get(
                "termination_reason_message",
                instance_model.termination_reason_message,
            ),
        )
        _emit_instance_health_change_event(
            session=session,
            instance_model=instance_model,
            old_health=instance_model.health,
            new_health=result.instance_update_map.get("health", instance_model.health),
        )
        _emit_instance_reachability_change_event(
            session=session,
            instance_model=instance_model,
            old_status=instance_model.status,
            old_unreachable=instance_model.unreachable,
            new_unreachable=result.instance_update_map.get(
                "unreachable", instance_model.unreachable
            ),
        )


def _emit_instance_health_change_event(
    session: AsyncSession,
    instance_model: InstanceModel,
    old_health: HealthStatus,
    new_health: HealthStatus,
) -> None:
    if old_health == new_health:
        return
    events.emit(
        session,
        f"Instance health changed {old_health.upper()} -> {new_health.upper()}",
        actor=events.SystemActor(),
        targets=[events.Target.from_model(instance_model)],
    )


def _emit_instance_reachability_change_event(
    session: AsyncSession,
    instance_model: InstanceModel,
    old_status: InstanceStatus,
    old_unreachable: bool,
    new_unreachable: bool,
) -> None:
    if not old_status.is_available() or old_unreachable == new_unreachable:
        return
    events.emit(
        session,
        "Instance became unreachable" if new_unreachable else "Instance became reachable",
        actor=events.SystemActor(),
        targets=[events.Target.from_model(instance_model)],
    )
