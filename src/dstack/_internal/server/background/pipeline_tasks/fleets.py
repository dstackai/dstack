import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Sequence, TypedDict

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import joinedload, load_only, selectinload

from dstack._internal.core.models.fleets import (
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.core.models.runs import RunStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    NOW_PLACEHOLDER,
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
    UpdateMapDateTime,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_changed_on_reset,
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    RunModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.fleets import (
    create_fleet_instance_model,
    emit_fleet_status_change_event,
    get_fleet_spec,
    get_next_instance_num,
    is_fleet_empty,
    is_fleet_in_use,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class FleetPipeline(Pipeline[PipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=60),
        lock_timeout: timedelta = timedelta(seconds=20),
        heartbeat_trigger: timedelta = timedelta(seconds=10),
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
            model_type=FleetModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = FleetFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            FleetWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return FleetModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[PipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[PipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["FleetWorker"]:
        return self.__workers


class FleetFetcher(Fetcher[PipelineItem]):
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

    @sentry_utils.instrument_named_task("pipeline_tasks.FleetFetcher.fetch")
    async def fetch(self, limit: int) -> list[PipelineItem]:
        fleet_lock, _ = get_locker(get_db().dialect_name).get_lockset(FleetModel.__tablename__)
        async with fleet_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(FleetModel)
                    .where(
                        FleetModel.deleted == False,
                        or_(
                            FleetModel.last_processed_at <= now - self._min_processing_interval,
                            FleetModel.last_processed_at == FleetModel.created_at,
                        ),
                        or_(
                            FleetModel.lock_expires_at.is_(None),
                            FleetModel.lock_expires_at < now,
                        ),
                        or_(
                            FleetModel.lock_owner.is_(None),
                            FleetModel.lock_owner == FleetPipeline.__name__,
                        ),
                    )
                    .order_by(FleetModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=FleetModel)
                    .options(
                        load_only(
                            FleetModel.id,
                            FleetModel.lock_token,
                            FleetModel.lock_expires_at,
                        )
                    )
                )
                fleet_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for fleet_model in fleet_models:
                    prev_lock_expired = fleet_model.lock_expires_at is not None
                    fleet_model.lock_expires_at = lock_expires_at
                    fleet_model.lock_token = lock_token
                    fleet_model.lock_owner = FleetPipeline.__name__
                    items.append(
                        PipelineItem(
                            __tablename__=FleetModel.__tablename__,
                            id=fleet_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                        )
                    )
                await session.commit()
        return items


class FleetWorker(Worker[PipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        heartbeater: Heartbeater[PipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.FleetWorker.process")
    async def process(self, item: PipelineItem):
        process_context = await _load_process_context(item)
        if process_context is None:
            return
        result = await _process_fleet(
            process_context.fleet_model,
            consolidation_fleet_spec=process_context.consolidation_fleet_spec,
            consolidation_instances=process_context.consolidation_instances,
        )
        await _apply_process_result(item, process_context, result)


@dataclass
class _ProcessContext:
    fleet_model: FleetModel
    consolidation_fleet_spec: Optional[FleetSpec]
    consolidation_instances: Optional[list[InstanceModel]]
    locked_instance_ids: set[uuid.UUID] = field(default_factory=set)


class _FleetUpdateMap(ItemUpdateMap, total=False):
    status: FleetStatus
    status_message: str
    deleted: bool
    deleted_at: UpdateMapDateTime
    consolidation_attempt: int
    last_consolidated_at: UpdateMapDateTime
    current_master_instance_id: Optional[uuid.UUID]


class _InstanceUpdateMap(ItemUpdateMap, total=False):
    status: InstanceStatus
    termination_reason: InstanceTerminationReason
    termination_reason_message: str
    deleted: bool
    deleted_at: UpdateMapDateTime
    last_processed_at: UpdateMapDateTime
    id: uuid.UUID


@dataclass
class _ProcessResult:
    fleet_update_map: _FleetUpdateMap = field(default_factory=_FleetUpdateMap)
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap] = field(default_factory=dict)
    new_instance_creates: list["_NewInstanceCreate"] = field(default_factory=list)


class _NewInstanceCreate(TypedDict):
    id: uuid.UUID
    instance_num: int


@dataclass
class _MaintainNodesResult:
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap] = field(default_factory=dict)
    new_instance_creates: list[_NewInstanceCreate] = field(default_factory=list)
    changes_required: bool = False

    @property
    def has_changes(self) -> bool:
        return len(self.instance_id_to_update_map) > 0 or len(self.new_instance_creates) > 0


async def _load_process_context(item: PipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        fleet_model = await _refetch_locked_fleet(session=session, item=item)
        if fleet_model is None:
            log_lock_token_mismatch(logger, item)
            return None

        consolidation_fleet_spec = _get_fleet_spec_if_ready_for_consolidation(fleet_model)
        consolidation_instances = None
        if consolidation_fleet_spec is not None:
            consolidation_instances = await _lock_fleet_instances_for_consolidation(
                session=session,
                item=item,
            )
            if consolidation_instances is None:
                return None

        return _ProcessContext(
            fleet_model=fleet_model,
            consolidation_fleet_spec=consolidation_fleet_spec,
            consolidation_instances=consolidation_instances,
            locked_instance_ids=(
                set()
                if consolidation_instances is None
                else {i.id for i in consolidation_instances}
            ),
        )


async def _refetch_locked_fleet(
    session: AsyncSession,
    item: PipelineItem,
) -> Optional[FleetModel]:
    res = await session.execute(
        select(FleetModel)
        .where(
            FleetModel.id == item.id,
            FleetModel.lock_token == item.lock_token,
        )
        .options(joinedload(FleetModel.project))
        .options(
            selectinload(FleetModel.instances.and_(InstanceModel.deleted == False))
            .joinedload(InstanceModel.jobs)
            .load_only(JobModel.id),
        )
        .options(
            selectinload(
                FleetModel.runs.and_(RunModel.status.not_in(RunStatus.finished_statuses()))
            ).load_only(RunModel.status)
        )
    )
    return res.unique().scalar_one_or_none()


def _get_fleet_spec_if_ready_for_consolidation(fleet_model: FleetModel) -> Optional[FleetSpec]:
    if fleet_model.status == FleetStatus.TERMINATING:
        return None
    consolidation_fleet_spec = get_fleet_spec(fleet_model)
    if (
        consolidation_fleet_spec.configuration.nodes is None
        or consolidation_fleet_spec.autocreated
    ):
        return None
    if not _is_fleet_ready_for_consolidation(fleet_model):
        return None
    return consolidation_fleet_spec


async def _lock_fleet_instances_for_consolidation(
    session: AsyncSession,
    item: PipelineItem,
) -> Optional[list[InstanceModel]]:
    instance_lock, _ = get_locker(get_db().dialect_name).get_lockset(InstanceModel.__tablename__)
    async with instance_lock:
        res = await session.execute(
            select(InstanceModel)
            .where(
                InstanceModel.fleet_id == item.id,
                InstanceModel.deleted == False,
                or_(
                    InstanceModel.lock_expires_at.is_(None),
                    InstanceModel.lock_expires_at < get_current_datetime(),
                ),
                or_(
                    InstanceModel.lock_owner.is_(None),
                    InstanceModel.lock_owner == FleetPipeline.__name__,
                ),
            )
            .with_for_update(skip_locked=True, key_share=True, of=InstanceModel)
        )
        locked_instance_models = list(res.scalars().all())
        locked_instance_ids = {instance_model.id for instance_model in locked_instance_models}

        res = await session.execute(
            select(InstanceModel.id).where(
                InstanceModel.fleet_id == item.id,
                InstanceModel.deleted == False,
            )
        )
        current_instance_ids = set(res.scalars().all())
        if current_instance_ids != locked_instance_ids:
            logger.debug(
                "Failed to lock fleet %s instances. The fleet will be processed later.",
                item.id,
            )
            # Keep `lock_owner` so that `InstancePipeline` can check that the fleet is being locked
            # but unset `lock_expires_at` to process the item again ASAP (after `min_processing_interval`).
            # Unset `lock_token` so that heartbeater can no longer update the item.
            res = await session.execute(
                update(FleetModel)
                .where(
                    FleetModel.id == item.id,
                    FleetModel.lock_token == item.lock_token,
                )
                .values(
                    lock_expires_at=None,
                    lock_token=None,
                    last_processed_at=get_current_datetime(),
                )
                .returning(FleetModel.id)
            )
            updated_ids = list(res.scalars().all())
            if len(updated_ids) == 0:
                log_lock_token_changed_on_reset(logger)
            return None

        for instance_model in locked_instance_models:
            instance_model.lock_expires_at = item.lock_expires_at
            instance_model.lock_token = item.lock_token
            instance_model.lock_owner = FleetPipeline.__name__
        await session.commit()
        return locked_instance_models


async def _apply_process_result(
    item: PipelineItem,
    context: _ProcessContext,
    result: "_ProcessResult",
) -> None:
    fleet_update_map = _FleetUpdateMap()
    fleet_update_map.update(result.fleet_update_map)
    set_processed_update_map_fields(fleet_update_map)
    set_unlock_update_map_fields(fleet_update_map)
    instance_update_rows = _build_instance_update_rows(
        result.instance_id_to_update_map,
        unlock_instance_ids=context.locked_instance_ids,
    )

    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(fleet_update_map, now=now)
        resolve_now_placeholders(instance_update_rows, now=now)
        res = await session.execute(
            update(FleetModel)
            .where(
                FleetModel.id == context.fleet_model.id,
                FleetModel.lock_token == context.fleet_model.lock_token,
            )
            .values(**fleet_update_map)
            .returning(FleetModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            if context.locked_instance_ids:
                await _unlock_fleet_locked_instances(
                    session=session,
                    item=item,
                    locked_instance_ids=context.locked_instance_ids,
                )
            # TODO: Clean up fleet.
            return

        if fleet_update_map.get("deleted"):
            await session.execute(
                update(PlacementGroupModel)
                .where(PlacementGroupModel.fleet_id == context.fleet_model.id)
                .values(fleet_deleted=True)
            )
        if instance_update_rows:
            await session.execute(
                update(InstanceModel),
                instance_update_rows,
            )
        if len(result.new_instance_creates) > 0:
            await _create_missing_fleet_instances(
                session=session,
                fleet_model=context.fleet_model,
                new_instance_creates=result.new_instance_creates,
            )
        emit_fleet_status_change_event(
            session=session,
            fleet_model=context.fleet_model,
            old_status=context.fleet_model.status,
            new_status=fleet_update_map.get("status", context.fleet_model.status),
            status_message=fleet_update_map.get(
                "status_message", context.fleet_model.status_message
            ),
        )


async def _process_fleet(
    fleet_model: FleetModel,
    consolidation_fleet_spec: Optional[FleetSpec] = None,
    consolidation_instances: Optional[Sequence[InstanceModel]] = None,
) -> _ProcessResult:
    result = _ProcessResult()
    effective_instances = list(consolidation_instances or fleet_model.instances)
    if consolidation_fleet_spec is not None:
        result = _consolidate_fleet_state_with_spec(
            fleet_model,
            consolidation_fleet_spec=consolidation_fleet_spec,
            consolidation_instances=effective_instances,
        )
    if len(result.new_instance_creates) == 0 and _should_delete_fleet(fleet_model):
        result.fleet_update_map["status"] = FleetStatus.TERMINATED
        result.fleet_update_map["deleted"] = True
        result.fleet_update_map["deleted_at"] = NOW_PLACEHOLDER
    _set_fail_instances_on_master_bootstrap_failure(
        fleet_model=fleet_model,
        instance_models=effective_instances,
        instance_id_to_update_map=result.instance_id_to_update_map,
    )
    _set_current_master_instance_id(
        fleet_model=fleet_model,
        fleet_update_map=result.fleet_update_map,
        instance_models=effective_instances,
        instance_id_to_update_map=result.instance_id_to_update_map,
        new_instance_creates=result.new_instance_creates,
    )
    return result


def _consolidate_fleet_state_with_spec(
    fleet_model: FleetModel,
    consolidation_fleet_spec: FleetSpec,
    consolidation_instances: Sequence[InstanceModel],
) -> _ProcessResult:
    result = _ProcessResult()
    maintain_nodes_result = _maintain_fleet_nodes_in_min_max_range(
        instances=consolidation_instances,
        fleet_spec=consolidation_fleet_spec,
    )
    if maintain_nodes_result.has_changes:
        result.instance_id_to_update_map = maintain_nodes_result.instance_id_to_update_map
        result.new_instance_creates = maintain_nodes_result.new_instance_creates
    if maintain_nodes_result.changes_required:
        result.fleet_update_map["consolidation_attempt"] = fleet_model.consolidation_attempt + 1
    else:
        # The fleet is consolidated with respect to nodes min/max.
        result.fleet_update_map["consolidation_attempt"] = 0
    result.fleet_update_map["last_consolidated_at"] = NOW_PLACEHOLDER
    return result


def _is_fleet_ready_for_consolidation(fleet_model: FleetModel) -> bool:
    consolidation_retry_delay = _get_consolidation_retry_delay(fleet_model.consolidation_attempt)
    last_consolidated_at = fleet_model.last_consolidated_at or fleet_model.last_processed_at
    duration_since_last_consolidation = get_current_datetime() - last_consolidated_at
    return duration_since_last_consolidation >= consolidation_retry_delay


# We use exponentially increasing consolidation retry delays so that
# consolidation does not happen too often. In particular, this prevents
# retrying instance provisioning constantly in case of no offers.
_CONSOLIDATION_RETRY_DELAYS = [
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=10),
    timedelta(minutes=30),
]


def _get_consolidation_retry_delay(consolidation_attempt: int) -> timedelta:
    if consolidation_attempt < len(_CONSOLIDATION_RETRY_DELAYS):
        return _CONSOLIDATION_RETRY_DELAYS[consolidation_attempt]
    return _CONSOLIDATION_RETRY_DELAYS[-1]


def _maintain_fleet_nodes_in_min_max_range(
    instances: Sequence[InstanceModel],
    fleet_spec: FleetSpec,
) -> _MaintainNodesResult:
    """
    Ensures the fleet has at least `nodes.min` and at most `nodes.max` instances.
    """
    assert fleet_spec.configuration.nodes is not None
    result = _MaintainNodesResult()
    for instance in instances:
        # Delete terminated but not deleted instances since
        # they are going to be replaced with new pending instances.
        if instance.status == InstanceStatus.TERMINATED and not instance.deleted:
            result.changes_required = True
            result.instance_id_to_update_map[instance.id] = {
                "deleted": True,
                "deleted_at": NOW_PLACEHOLDER,
            }
    active_instances = [
        i for i in instances if i.status != InstanceStatus.TERMINATED and not i.deleted
    ]
    active_instances_num = len(active_instances)
    if active_instances_num < fleet_spec.configuration.nodes.min:
        result.changes_required = True
        nodes_missing = fleet_spec.configuration.nodes.min - active_instances_num
        taken_instance_nums = {instance.instance_num for instance in active_instances}
        for _ in range(nodes_missing):
            instance_num = get_next_instance_num(taken_instance_nums)
            taken_instance_nums.add(instance_num)
            result.new_instance_creates.append(
                _NewInstanceCreate(id=uuid.uuid4(), instance_num=instance_num)
            )
        return result
    if (
        fleet_spec.configuration.nodes.max is None
        or active_instances_num <= fleet_spec.configuration.nodes.max
    ):
        return result
    # Fleet has more instances than allowed by nodes.max.
    # This is possible due to race conditions (e.g. provisioning jobs in a fleet concurrently)
    # or if nodes.max is updated.
    result.changes_required = True
    nodes_redundant = active_instances_num - fleet_spec.configuration.nodes.max
    for instance in instances:
        if nodes_redundant == 0:
            break
        if instance.status == InstanceStatus.IDLE:
            result.instance_id_to_update_map[instance.id] = {
                "termination_reason": InstanceTerminationReason.MAX_INSTANCES_LIMIT,
                "termination_reason_message": "Fleet has too many instances",
                "status": InstanceStatus.TERMINATING,
            }
            nodes_redundant -= 1
    return result


def _should_delete_fleet(fleet_model: FleetModel) -> bool:
    if fleet_model.project.deleted:
        # It used to be possible to delete project with active resources:
        # https://github.com/dstackai/dstack/issues/3077
        logger.info("Fleet %s deleted due to deleted project", fleet_model.name)
        return True

    if is_fleet_in_use(fleet_model) or not is_fleet_empty(fleet_model):
        return False

    # TODO: Drop non-terminating fleets auto-deletion after dropping fleets auto-creation.
    fleet_spec = get_fleet_spec(fleet_model)
    if (
        fleet_model.status != FleetStatus.TERMINATING
        and fleet_spec.configuration.nodes is not None
        and fleet_spec.configuration.nodes.min == 0
    ):
        # Empty fleets that allow 0 nodes should not be auto-deleted
        return False

    logger.info("Automatic cleanup of an empty fleet %s", fleet_model.name)
    return True


def _build_instance_update_rows(
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap],
    unlock_instance_ids: set[uuid.UUID],
) -> list[_InstanceUpdateMap]:
    instance_update_rows = []
    for instance_id in sorted(instance_id_to_update_map.keys() | unlock_instance_ids):
        instance_update_map = instance_id_to_update_map.get(instance_id)
        update_row = _InstanceUpdateMap()
        if instance_update_map is not None:
            update_row.update(instance_update_map)
        if instance_id in unlock_instance_ids:
            set_unlock_update_map_fields(update_row)
        update_row["id"] = instance_id
        set_processed_update_map_fields(update_row)
        instance_update_rows.append(update_row)
    return instance_update_rows


async def _unlock_fleet_locked_instances(
    session: AsyncSession,
    item: PipelineItem,
    locked_instance_ids: set[uuid.UUID],
) -> None:
    await session.execute(
        update(InstanceModel)
        .where(
            InstanceModel.id.in_(locked_instance_ids),
            InstanceModel.lock_token == item.lock_token,
            InstanceModel.lock_owner == FleetPipeline.__name__,
        )
        .values(
            lock_expires_at=None,
            lock_token=None,
            lock_owner=None,
        )
    )


async def _create_missing_fleet_instances(
    session: AsyncSession,
    fleet_model: FleetModel,
    new_instance_creates: Sequence[_NewInstanceCreate],
):
    fleet_spec = get_fleet_spec(fleet_model)
    for new_instance_create in new_instance_creates:
        instance_model = create_fleet_instance_model(
            session=session,
            project=fleet_model.project,
            # TODO: Store fleet.user and pass it instead of the project owner.
            username=fleet_model.project.owner.name,
            spec=fleet_spec,
            instance_num=new_instance_create["instance_num"],
            instance_id=new_instance_create["id"],
        )
        instance_model.fleet_id = fleet_model.id
        events.emit(
            session=session,
            message=(
                "Instance created to meet target fleet node count."
                f" Status: {instance_model.status.upper()}"
            ),
            actor=events.SystemActor(),
            targets=[events.Target.from_model(instance_model)],
        )
    logger.info(
        "Added %d instances to fleet %s",
        len(new_instance_creates),
        fleet_model.name,
    )


def _set_fail_instances_on_master_bootstrap_failure(
    fleet_model: FleetModel,
    instance_models: Sequence[InstanceModel],
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap],
) -> None:
    """
    Terminates instances with MASTER_FAILED if the master dies with NO_OFFERS in a cluster with node.min == 0.
    This is needed to avoid master re-election loop and fail fast.
    """
    fleet_spec = get_fleet_spec(fleet_model)
    if (
        not _is_cloud_cluster_fleet_spec(fleet_spec)
        or fleet_spec.configuration.nodes is None
        or fleet_spec.configuration.nodes.min != 0
        or fleet_model.current_master_instance_id is None
    ):
        return

    current_master_instance_model = None
    for instance_model in instance_models:
        if instance_model.id == fleet_model.current_master_instance_id:
            current_master_instance_model = instance_model
            break
    if current_master_instance_model is None:
        return

    if (
        current_master_instance_model.status != InstanceStatus.TERMINATED
        or current_master_instance_model.termination_reason != InstanceTerminationReason.NO_OFFERS
    ):
        return

    surviving_instance_models = _get_surviving_instance_models_after_updates(
        instance_models=instance_models,
        instance_id_to_update_map=instance_id_to_update_map,
    )
    if any(
        instance_model.status not in InstanceStatus.finished_statuses()
        and instance_model.job_provisioning_data is not None
        for instance_model in surviving_instance_models
    ):
        # It should not be possible to provision non-master instances ahead of master
        # but we still safe-guard against the case when there can be other instances provisioned.
        return

    for instance_model in surviving_instance_models:
        if (
            instance_model.id == current_master_instance_model.id
            or instance_model.status in InstanceStatus.finished_statuses()
        ):
            continue
        update_map = instance_id_to_update_map.setdefault(instance_model.id, _InstanceUpdateMap())
        update_map["status"] = InstanceStatus.TERMINATED
        update_map["termination_reason"] = InstanceTerminationReason.MASTER_FAILED


def _set_current_master_instance_id(
    fleet_model: FleetModel,
    fleet_update_map: _FleetUpdateMap,
    instance_models: Sequence[InstanceModel],
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap],
    new_instance_creates: Sequence[_NewInstanceCreate],
) -> None:
    """
    Sets `current_master_instance_id` for `fleet_model`.
    Master instance can be changed if the previous master is gone.
    If there are no active instances, newly selected master may change backend/region/az/placement.
    """
    fleet_spec = get_fleet_spec(fleet_model)
    if not _is_cloud_cluster_fleet_spec(fleet_spec):
        fleet_update_map["current_master_instance_id"] = None
        return
    surviving_instance_models = _get_surviving_instance_models_after_updates(
        instance_models=instance_models,
        instance_id_to_update_map=instance_id_to_update_map,
    )
    current_master_instance_id = _select_current_master_instance_id(
        current_master_instance_id=fleet_model.current_master_instance_id,
        surviving_instance_models=surviving_instance_models,
        instance_id_to_update_map=instance_id_to_update_map,
        new_instance_creates=new_instance_creates,
    )
    fleet_update_map["current_master_instance_id"] = current_master_instance_id


def _get_surviving_instance_models_after_updates(
    instance_models: Sequence[InstanceModel],
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap],
) -> list[InstanceModel]:
    surviving_instance_models = []
    for instance_model in sorted(instance_models, key=lambda i: (i.instance_num, i.created_at)):
        instance_update_map = instance_id_to_update_map.get(instance_model.id)
        if instance_update_map is not None and instance_update_map.get("deleted"):
            continue
        surviving_instance_models.append(instance_model)
    return surviving_instance_models


def _select_current_master_instance_id(
    current_master_instance_id: Optional[uuid.UUID],
    surviving_instance_models: Sequence[InstanceModel],
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap],
    new_instance_creates: Sequence[_NewInstanceCreate],
) -> Optional[uuid.UUID]:
    # Keep the current master stable while it is still alive so InstancePipeline
    # does not see fleet-wide election churn between provisioning attempts.
    if current_master_instance_id is not None:
        for instance_model in surviving_instance_models:
            if (
                instance_model.id == current_master_instance_id
                and _get_effective_instance_status(
                    instance_model,
                    instance_id_to_update_map=instance_id_to_update_map,
                )
                not in InstanceStatus.finished_statuses()
            ):
                return instance_model.id

    # If the old master is gone, prefer a surviving provisioned instance so we
    # keep following an already-established cluster placement decision.
    for instance_model in surviving_instance_models:
        if (
            _get_effective_instance_status(
                instance_model,
                instance_id_to_update_map=instance_id_to_update_map,
            )
            not in InstanceStatus.finished_statuses()
            and instance_model.job_provisioning_data is not None
        ):
            return instance_model.id

    # Prefer existing surviving instances over freshly planned replacements to
    # avoid election churn during min-nodes backfill.
    for instance_model in surviving_instance_models:
        if (
            _get_effective_instance_status(
                instance_model,
                instance_id_to_update_map=instance_id_to_update_map,
            )
            not in InstanceStatus.finished_statuses()
        ):
            return instance_model.id

    for new_instance_create in sorted(new_instance_creates, key=lambda i: i["instance_num"]):
        return new_instance_create["id"]

    return None


def _get_effective_instance_status(
    instance_model: InstanceModel,
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap],
) -> InstanceStatus:
    update_map = instance_id_to_update_map.get(instance_model.id)
    if update_map is None:
        return instance_model.status
    return update_map.get("status", instance_model.status)


def _is_cloud_cluster_fleet_spec(fleet_spec: FleetSpec) -> bool:
    configuration = fleet_spec.configuration
    return (
        configuration.placement == InstanceGroupPlacement.CLUSTER
        and configuration.ssh_config is None
    )
