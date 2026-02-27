import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Sequence, TypedDict

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import joinedload, load_only, selectinload

from dstack._internal.core.models.fleets import FleetSpec, FleetStatus
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
        min_processing_interval: timedelta = timedelta(seconds=30),
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
                    .with_for_update(skip_locked=True, key_share=True)
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
        async with get_session_ctx() as session:
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
            fleet_model = res.unique().scalar_one_or_none()
            if fleet_model is None:
                logger.warning(
                    "Failed to process %s item %s: lock_token mismatch."
                    " The item is expected to be processed and updated on another fetch iteration.",
                    item.__tablename__,
                    item.id,
                )
                return

            instance_lock, _ = get_locker(get_db().dialect_name).get_lockset(
                InstanceModel.__tablename__
            )
            async with instance_lock:
                res = await session.execute(
                    select(InstanceModel)
                    .where(
                        InstanceModel.fleet_id == item.id,
                        InstanceModel.deleted == False,
                        # TODO: Lock instance models in the DB
                        # or_(
                        #     InstanceModel.lock_expires_at.is_(None),
                        #     InstanceModel.lock_expires_at < get_current_datetime(),
                        # ),
                        # or_(
                        #     InstanceModel.lock_owner.is_(None),
                        #     InstanceModel.lock_owner == FleetPipeline.__name__,
                        # ),
                    )
                    .with_for_update(skip_locked=True, key_share=True)
                )
                locked_instance_models = res.scalars().all()
                if len(fleet_model.instances) != len(locked_instance_models):
                    logger.debug(
                        "Failed to lock fleet %s instances. The fleet will be processed later.",
                        item.id,
                    )
                    now = get_current_datetime()
                    # Keep `lock_owner` so that `InstancePipeline` sees that the fleet is being locked
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
                            last_processed_at=now,
                        )
                    )
                    if res.rowcount == 0:  # pyright: ignore[reportAttributeAccessIssue]
                        logger.warning(
                            "Failed to reset lock: lock_token changed."
                            " The item is expected to be processed and updated on another fetch iteration."
                        )
                    return

                # TODO: Lock instance models in the DB
                # for instance_model in locked_instance_models:
                #     instance_model.lock_expires_at = item.lock_expires_at
                #     instance_model.lock_token = item.lock_token
                #     instance_model.lock_owner = FleetPipeline.__name__
                # await session.commit()

        result = await _process_fleet(fleet_model)
        fleet_update_map = _FleetUpdateMap()
        fleet_update_map.update(result.fleet_update_map)
        set_processed_update_map_fields(fleet_update_map)
        set_unlock_update_map_fields(fleet_update_map)
        instance_update_rows = _build_instance_update_rows(result.instance_id_to_update_map)

        async with get_session_ctx() as session:
            now = get_current_datetime()
            resolve_now_placeholders(fleet_update_map, now=now)
            resolve_now_placeholders(instance_update_rows, now=now)
            res = await session.execute(
                update(FleetModel)
                .where(
                    FleetModel.id == fleet_model.id,
                    FleetModel.lock_token == fleet_model.lock_token,
                )
                .values(**fleet_update_map)
                .returning(FleetModel.id)
            )
            updated_ids = list(res.scalars().all())
            if len(updated_ids) == 0:
                logger.warning(
                    "Failed to update %s item %s after processing: lock_token changed."
                    " The item is expected to be processed and updated on another fetch iteration.",
                    item.__tablename__,
                    item.id,
                )
                # TODO: Clean up fleet.
                return

            if fleet_update_map.get("deleted"):
                await session.execute(
                    update(PlacementGroupModel)
                    .where(PlacementGroupModel.fleet_id == item.id)
                    .values(fleet_deleted=True)
                )
            if instance_update_rows:
                await session.execute(
                    update(InstanceModel).execution_options(synchronize_session=False),
                    instance_update_rows,
                )
            if result.new_instances_count > 0:
                await _create_missing_fleet_instances(
                    session=session,
                    fleet_model=fleet_model,
                    new_instances_count=result.new_instances_count,
                )
            emit_fleet_status_change_event(
                session=session,
                fleet_model=fleet_model,
                old_status=fleet_model.status,
                new_status=fleet_update_map.get("status", fleet_model.status),
                status_message=fleet_update_map.get("status_message", fleet_model.status_message),
            )


class _FleetUpdateMap(ItemUpdateMap, total=False):
    status: FleetStatus
    status_message: str
    deleted: bool
    deleted_at: UpdateMapDateTime
    consolidation_attempt: int
    last_consolidated_at: UpdateMapDateTime


class _InstanceUpdateMap(TypedDict, total=False):
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
    new_instances_count: int = 0


@dataclass
class _MaintainNodesResult:
    instance_id_to_update_map: dict[uuid.UUID, _InstanceUpdateMap] = field(default_factory=dict)
    new_instances_count: int = 0
    changes_required: bool = False

    @property
    def has_changes(self) -> bool:
        return len(self.instance_id_to_update_map) > 0 or self.new_instances_count > 0


async def _process_fleet(fleet_model: FleetModel) -> _ProcessResult:
    result = _consolidate_fleet_state_with_spec(fleet_model)
    if result.new_instances_count > 0:
        # Avoid auto-deleting empty fleets that are about to receive new instances.
        return result
    # TODO: Drop fleets auto-deletion after dropping fleets auto-creation.
    deleted = _autodelete_fleet(fleet_model)
    if deleted:
        result.fleet_update_map["status"] = FleetStatus.TERMINATED
        result.fleet_update_map["deleted"] = True
        result.fleet_update_map["deleted_at"] = NOW_PLACEHOLDER
    return result


def _consolidate_fleet_state_with_spec(fleet_model: FleetModel) -> _ProcessResult:
    result = _ProcessResult()
    if fleet_model.status == FleetStatus.TERMINATING:
        return result
    fleet_spec = get_fleet_spec(fleet_model)
    if fleet_spec.configuration.nodes is None or fleet_spec.autocreated:
        # Only explicitly created cloud fleets are consolidated.
        return result
    if not _is_fleet_ready_for_consolidation(fleet_model):
        return result
    maintain_nodes_result = _maintain_fleet_nodes_in_min_max_range(fleet_model, fleet_spec)
    if maintain_nodes_result.has_changes:
        result.instance_id_to_update_map = maintain_nodes_result.instance_id_to_update_map
        result.new_instances_count = maintain_nodes_result.new_instances_count
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
# TODO: Adjust delays.
_CONSOLIDATION_RETRY_DELAYS = [
    timedelta(seconds=30),
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=10),
]


def _get_consolidation_retry_delay(consolidation_attempt: int) -> timedelta:
    if consolidation_attempt < len(_CONSOLIDATION_RETRY_DELAYS):
        return _CONSOLIDATION_RETRY_DELAYS[consolidation_attempt]
    return _CONSOLIDATION_RETRY_DELAYS[-1]


def _maintain_fleet_nodes_in_min_max_range(
    fleet_model: FleetModel,
    fleet_spec: FleetSpec,
) -> _MaintainNodesResult:
    """
    Ensures the fleet has at least `nodes.min` and at most `nodes.max` instances.
    """
    assert fleet_spec.configuration.nodes is not None
    result = _MaintainNodesResult()
    for instance in fleet_model.instances:
        # Delete terminated but not deleted instances since
        # they are going to be replaced with new pending instances.
        if instance.status == InstanceStatus.TERMINATED and not instance.deleted:
            result.changes_required = True
            result.instance_id_to_update_map[instance.id] = {
                "deleted": True,
                "deleted_at": NOW_PLACEHOLDER,
            }
    active_instances = [
        i for i in fleet_model.instances if i.status != InstanceStatus.TERMINATED and not i.deleted
    ]
    active_instances_num = len(active_instances)
    if active_instances_num < fleet_spec.configuration.nodes.min:
        result.changes_required = True
        nodes_missing = fleet_spec.configuration.nodes.min - active_instances_num
        result.new_instances_count = nodes_missing
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
    for instance in fleet_model.instances:
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


def _autodelete_fleet(fleet_model: FleetModel) -> bool:
    if fleet_model.project.deleted:
        # It used to be possible to delete project with active resources:
        # https://github.com/dstackai/dstack/issues/3077
        logger.info("Fleet %s deleted due to deleted project", fleet_model.name)
        return True

    if is_fleet_in_use(fleet_model) or not is_fleet_empty(fleet_model):
        return False

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
) -> list[_InstanceUpdateMap]:
    instance_update_rows = []
    for instance_id, instance_update_map in instance_id_to_update_map.items():
        update_row = _InstanceUpdateMap()
        update_row.update(instance_update_map)
        update_row["id"] = instance_id
        set_processed_update_map_fields(update_row)
        instance_update_rows.append(update_row)
    return instance_update_rows


async def _create_missing_fleet_instances(
    session: AsyncSession,
    fleet_model: FleetModel,
    new_instances_count: int,
):
    fleet_spec = get_fleet_spec(fleet_model)
    res = await session.execute(
        select(InstanceModel.instance_num).where(
            InstanceModel.fleet_id == fleet_model.id,
            InstanceModel.deleted == False,
        )
    )
    taken_instance_nums = set(res.scalars().all())
    for _ in range(new_instances_count):
        instance_num = get_next_instance_num(taken_instance_nums)
        instance_model = create_fleet_instance_model(
            session=session,
            project=fleet_model.project,
            # TODO: Store fleet.user and pass it instead of the project owner.
            username=fleet_model.project.owner.name,
            spec=fleet_spec,
            instance_num=instance_num,
        )
        instance_model.fleet_id = fleet_model.id
        taken_instance_nums.add(instance_num)
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
        new_instances_count,
        fleet_model.name,
    )
