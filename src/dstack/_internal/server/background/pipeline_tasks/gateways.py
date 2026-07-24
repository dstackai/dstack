import asyncio
import itertools
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Sequence

from sqlalchemy import ColumnElement, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only, selectinload

from dstack._internal.core.models.gateways import (
    GATEWAY_REPLICAS_DEFAULT,
    GatewayReplicaStatus,
    GatewayStatus,
)
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
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    BackendModel,
    GatewayComputeModel,
    GatewayModel,
    ProjectModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services import gateways as gateways_services
from dstack._internal.server.services.gateways import (
    emit_gateway_status_change_event,
    get_gateway_compute_models,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.utils import tracing
from dstack._internal.utils.common import get_current_datetime, get_lowest_unused_nums
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GatewayPipelineItem(PipelineItem):
    status: GatewayStatus
    to_be_deleted: bool


class GatewayPipeline(Pipeline[GatewayPipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=15),
        lock_timeout: timedelta = timedelta(seconds=30),
        heartbeat_trigger: timedelta = timedelta(seconds=15),
        *,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[GatewayPipelineItem](
            model_type=GatewayModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = GatewayFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            GatewayWorker(
                queue=self._queue,
                heartbeater=self._heartbeater,
                pipeline_hinter=pipeline_hinter,
            )
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return GatewayModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[GatewayPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[GatewayPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["GatewayWorker"]:
        return self.__workers


class GatewayFetcher(Fetcher[GatewayPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[GatewayPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[GatewayPipelineItem],
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

    @tracing.instrument_pipeline_task("GatewayFetcher.fetch")
    async def fetch(self, limit: int) -> list[GatewayPipelineItem]:
        gateway_lock, _ = get_locker(get_db().dialect_name).get_lockset(GatewayModel.__tablename__)
        async with gateway_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                active_replica_count_subquery = (
                    select(func.count(GatewayComputeModel.id))
                    .where(
                        or_(
                            GatewayComputeModel.gateway_id == GatewayModel.id,
                            GatewayComputeModel.id == GatewayModel.gateway_compute_id,
                        ),
                        *_get_active_replica_filters(),
                    )
                    .correlate(GatewayModel)
                    .scalar_subquery()
                )
                res = await session.execute(
                    select(GatewayModel)
                    .where(
                        or_(
                            GatewayModel.status.in_(
                                [GatewayStatus.SUBMITTED, GatewayStatus.PROVISIONING]
                            ),
                            and_(
                                GatewayModel.status == GatewayStatus.RUNNING,
                                GatewayModel.desired_replica_count.is_not(None),
                                or_(
                                    # fetch to reconcile replica count
                                    GatewayModel.desired_replica_count
                                    != active_replica_count_subquery,
                                    # fetch to potentially reset attempts
                                    GatewayModel.replica_scale_attempt > 0,
                                ),
                            ),
                            GatewayModel.to_be_deleted == True,
                        ),
                        or_(
                            GatewayModel.last_processed_at <= now - self._min_processing_interval,
                            GatewayModel.last_processed_at == GatewayModel.created_at,
                        ),
                        or_(
                            GatewayModel.lock_expires_at.is_(None),
                            GatewayModel.lock_expires_at < now,
                        ),
                        or_(
                            GatewayModel.lock_owner.is_(None),
                            GatewayModel.lock_owner == GatewayPipeline.__name__,
                        ),
                    )
                    .order_by(GatewayModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=GatewayModel)
                    .options(
                        load_only(
                            GatewayModel.id,
                            GatewayModel.lock_token,
                            GatewayModel.lock_expires_at,
                            GatewayModel.status,
                            GatewayModel.to_be_deleted,
                        )
                    )
                )
                gateway_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for gateway_model in gateway_models:
                    prev_lock_expired = gateway_model.lock_expires_at is not None
                    gateway_model.lock_expires_at = lock_expires_at
                    gateway_model.lock_token = lock_token
                    gateway_model.lock_owner = GatewayPipeline.__name__
                    items.append(
                        GatewayPipelineItem(
                            __tablename__=GatewayModel.__tablename__,
                            id=gateway_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=gateway_model.status,
                            to_be_deleted=gateway_model.to_be_deleted,
                        )
                    )
                await session.commit()
        return items


class GatewayWorker(Worker[GatewayPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[GatewayPipelineItem],
        heartbeater: Heartbeater[GatewayPipelineItem],
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
            pipeline_hinter=pipeline_hinter,
        )

    @tracing.instrument_pipeline_task("GatewayWorker.process")
    async def process(self, item: GatewayPipelineItem):
        if item.to_be_deleted:
            await _process_to_be_deleted_item(item)
        elif item.status == GatewayStatus.SUBMITTED:
            await _process_submitted_item(item)
        elif item.status == GatewayStatus.PROVISIONING:
            await _process_provisioning_item(item)
        elif item.status == GatewayStatus.RUNNING:
            await _process_running_item(item)


class _GatewayUpdateMap(ItemUpdateMap, total=False):
    status: GatewayStatus
    status_message: str
    replica_scale_attempt: int
    last_replica_scale_attempt_at: UpdateMapDateTime


@dataclass
class _ReplicaScalingResult:
    needs_more_replicas: bool = False
    new_gateway_compute_models: list[GatewayComputeModel] = field(default_factory=list)
    scale_in_replica_ids: list[uuid.UUID] = field(default_factory=list)
    gateway_update_map: _GatewayUpdateMap = field(default_factory=_GatewayUpdateMap)
    limit_reached: bool = False


async def _process_submitted_item(item: GatewayPipelineItem):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayModel)
            .where(
                GatewayModel.id == item.id,
                GatewayModel.lock_token == item.lock_token,
            )
            .options(joinedload(GatewayModel.project).load_only(ProjectModel.name))
            .options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
        )
        gateway_model = res.unique().scalar_one_or_none()
        if gateway_model is None:
            log_lock_token_mismatch(logger, item)
            return

    result = await _process_submitted_gateway(gateway_model)
    update_map = _GatewayUpdateMap()
    update_map.update(result.update_map)
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)
    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(update_map, now=now)
        res = await session.execute(
            update(GatewayModel)
            .where(
                GatewayModel.id == gateway_model.id,
                GatewayModel.lock_token == gateway_model.lock_token,
            )
            .values(**update_map)
            .returning(GatewayModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            return
        emit_gateway_status_change_event(
            session=session,
            gateway_model=gateway_model,
            old_status=gateway_model.status,
            new_status=update_map.get("status", gateway_model.status),
            status_message=update_map.get("status_message", gateway_model.status_message),
        )
        await _apply_replica_scaling(session, gateway_model, result.scale_result)


@dataclass
class _SubmittedResult:
    update_map: _GatewayUpdateMap = field(default_factory=_GatewayUpdateMap)
    scale_result: _ReplicaScalingResult = field(default_factory=_ReplicaScalingResult)


async def _process_submitted_gateway(gateway_model: GatewayModel) -> _SubmittedResult:
    # NOTE: On a later stage of #3959, the SUBMITTED status may also be responsible for
    # setting up the load balancer (e.g., AWS ALB) before replicas are created.
    scale_result = _reconcile_gateway_replica_count(gateway_model, gateway_replicas=[])
    update_map = _GatewayUpdateMap(status=GatewayStatus.PROVISIONING)
    update_map.update(scale_result.gateway_update_map)
    return _SubmittedResult(
        update_map=update_map,
        scale_result=scale_result,
    )


async def _process_provisioning_item(item: GatewayPipelineItem):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayModel)
            .where(
                GatewayModel.id == item.id,
                GatewayModel.lock_token == item.lock_token,
            )
            .options(joinedload(GatewayModel.project).load_only(ProjectModel.name))
            .options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
            .options(joinedload(GatewayModel.gateway_compute))
            .options(
                selectinload(GatewayModel.gateway_computes).load_only(
                    GatewayComputeModel.id,
                    GatewayComputeModel.status,
                    GatewayComputeModel.replica_num,
                    GatewayComputeModel.created_at,
                    GatewayComputeModel.scale_in,
                )
            )
        )
        gateway_model = res.unique().scalar_one_or_none()
        if gateway_model is None:
            log_lock_token_mismatch(logger, item)
            return

    result = _process_provisioning_gateway(gateway_model)
    gateway_update_map = result.gateway_update_map
    set_processed_update_map_fields(gateway_update_map)
    set_unlock_update_map_fields(gateway_update_map)

    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(gateway_update_map, now=now)
        res = await session.execute(
            update(GatewayModel)
            .where(
                GatewayModel.id == gateway_model.id,
                GatewayModel.lock_token == gateway_model.lock_token,
            )
            .values(**gateway_update_map)
            .returning(GatewayModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            return
        emit_gateway_status_change_event(
            session=session,
            gateway_model=gateway_model,
            old_status=gateway_model.status,
            new_status=gateway_update_map.get("status", gateway_model.status),
            status_message=gateway_update_map.get("status_message", gateway_model.status_message),
        )
        await _apply_replica_scaling(session, gateway_model, result.scale_result)


@dataclass
class _ProvisioningResult:
    gateway_update_map: _GatewayUpdateMap = field(default_factory=_GatewayUpdateMap)
    scale_result: _ReplicaScalingResult = field(default_factory=_ReplicaScalingResult)


def _process_provisioning_gateway(gateway_model: GatewayModel) -> _ProvisioningResult:
    gateway_computes = get_gateway_compute_models(gateway_model)
    # Provisioning gateways must have compute.
    assert len(gateway_computes) > 0

    scale_result = _reconcile_gateway_replica_count(gateway_model, gateway_computes)
    statuses = {
        gc.status
        for gc in gateway_computes
        if not gc.scale_in and gc.id not in scale_result.scale_in_replica_ids
    }

    if statuses & {GatewayReplicaStatus.TERMINATING, GatewayReplicaStatus.TERMINATED}:
        return _ProvisioningResult(
            gateway_update_map={
                "status": GatewayStatus.FAILED,
                "status_message": "Failed to provision gateway replica",
            },
            scale_result=_ReplicaScalingResult(),  # do not scale, gateway failed
        )

    update_map = _GatewayUpdateMap()
    update_map.update(scale_result.gateway_update_map)

    if statuses == {GatewayReplicaStatus.RUNNING} and not scale_result.needs_more_replicas:
        update_map["status"] = GatewayStatus.RUNNING
        return _ProvisioningResult(
            gateway_update_map=update_map,
            scale_result=scale_result,
        )

    # Replicas are still being provisioned
    return _ProvisioningResult(
        gateway_update_map=update_map,
        scale_result=scale_result,
    )


async def _process_running_item(item: GatewayPipelineItem):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayModel)
            .where(
                GatewayModel.id == item.id,
                GatewayModel.lock_token == item.lock_token,
            )
            .options(joinedload(GatewayModel.project).load_only(ProjectModel.name))
            .options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
            .options(joinedload(GatewayModel.gateway_compute))
            .options(
                selectinload(GatewayModel.gateway_computes).load_only(
                    GatewayComputeModel.id,
                    GatewayComputeModel.status,
                    GatewayComputeModel.replica_num,
                    GatewayComputeModel.created_at,
                    GatewayComputeModel.scale_in,
                )
            )
        )
        gateway_model = res.unique().scalar_one_or_none()
        if gateway_model is None:
            log_lock_token_mismatch(logger, item)
            return

    gateway_computes = get_gateway_compute_models(gateway_model)
    scale_result = _reconcile_gateway_replica_count(gateway_model, gateway_computes)

    update_map = _GatewayUpdateMap()
    update_map.update(scale_result.gateway_update_map)
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)
    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(update_map, now=now)
        res = await session.execute(
            update(GatewayModel)
            .where(
                GatewayModel.id == gateway_model.id,
                GatewayModel.lock_token == gateway_model.lock_token,
            )
            .values(**update_map)
            .returning(GatewayModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            return
        await _apply_replica_scaling(session, gateway_model, scale_result)


async def _process_to_be_deleted_item(item: GatewayPipelineItem):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayModel)
            .where(
                GatewayModel.id == item.id,
                GatewayModel.lock_token == item.lock_token,
            )
            .options(joinedload(GatewayModel.gateway_compute))
            .options(
                selectinload(GatewayModel.gateway_computes).load_only(
                    GatewayComputeModel.id, GatewayComputeModel.status
                )
            )
        )
        gateway_model = res.unique().scalar_one_or_none()
        if gateway_model is None:
            log_lock_token_mismatch(logger, item)
            return

    result = _process_to_be_deleted_gateway(gateway_model)
    async with get_session_ctx() as session:
        if result.delete_gateway:
            res = await session.execute(
                delete(GatewayModel)
                .where(
                    GatewayModel.id == gateway_model.id,
                    GatewayModel.lock_token == gateway_model.lock_token,
                )
                .returning(GatewayModel.id)
            )
            deleted_ids = list(res.scalars().all())
            if len(deleted_ids) == 0:
                log_lock_token_changed_after_processing(
                    logger,
                    item,
                    action="delete",
                    expected_outcome="deleted",
                )
                return
            events.emit(
                session,
                "Gateway deleted",
                actor=events.SystemActor(),
                targets=[events.Target.from_model(gateway_model)],
            )
        else:
            update_map = _GatewayUpdateMap()
            set_processed_update_map_fields(update_map)
            set_unlock_update_map_fields(update_map)
            resolve_now_placeholders(update_map, now=get_current_datetime())
            res = await session.execute(
                update(GatewayModel)
                .where(
                    GatewayModel.id == gateway_model.id,
                    GatewayModel.lock_token == gateway_model.lock_token,
                )
                .values(**update_map)
                .returning(GatewayModel.id)
            )
            updated_ids = list(res.scalars().all())
            if len(updated_ids) == 0:
                log_lock_token_changed_after_processing(logger, item)
                return


@dataclass
class _ProcessToBeDeletedResult:
    delete_gateway: bool


def _process_to_be_deleted_gateway(gateway_model: GatewayModel) -> _ProcessToBeDeletedResult:
    gateway_computes = get_gateway_compute_models(gateway_model)
    all_terminated = all(gc.status == GatewayReplicaStatus.TERMINATED for gc in gateway_computes)
    return _ProcessToBeDeletedResult(delete_gateway=all_terminated)


REPLICA_SCALE_IN_PRIORITY: dict[GatewayReplicaStatus, int] = {
    GatewayReplicaStatus.SUBMITTED: 0,
    GatewayReplicaStatus.PROVISIONING: 1,
    GatewayReplicaStatus.RUNNING: 2,
}


def _is_replica_active(replica: GatewayComputeModel) -> bool:
    # should match _get_active_replica_filters
    return not replica.scale_in and replica.status not in (
        GatewayReplicaStatus.TERMINATING,
        GatewayReplicaStatus.TERMINATED,
    )


def _get_active_replica_filters() -> list[ColumnElement[bool]]:
    # should match _is_replica_active
    return [
        GatewayComputeModel.scale_in == False,
        GatewayComputeModel.status.not_in(
            [GatewayReplicaStatus.TERMINATING, GatewayReplicaStatus.TERMINATED]
        ),
    ]


def _reconcile_gateway_replica_count(
    gateway_model: GatewayModel,
    gateway_replicas: list[GatewayComputeModel],
) -> _ReplicaScalingResult:
    desired_replica_count = gateway_model.desired_replica_count
    if desired_replica_count is None:  # pre-0.20.29 gateway
        if gateway_model.status != GatewayStatus.SUBMITTED:
            return _ReplicaScalingResult()
        desired_replica_count = gateways_services.get_gateway_configuration(gateway_model).replicas
        if desired_replica_count is None:
            desired_replica_count = GATEWAY_REPLICAS_DEFAULT

    reset_replica_scale_attempt = gateway_model.replica_scale_attempt > 0 and (
        _was_gateway_updated_since_last_scale_attempt(gateway_model)
    )

    active_replicas = [r for r in gateway_replicas if _is_replica_active(r)]
    diff = desired_replica_count - len(active_replicas)
    if diff == 0:
        result = _ReplicaScalingResult()
        if reset_replica_scale_attempt or (
            gateway_model.replica_scale_attempt > 0
            and all(r.status == GatewayReplicaStatus.RUNNING for r in active_replicas)
        ):
            result.gateway_update_map["replica_scale_attempt"] = 0
        return result

    if diff > 0:
        if not reset_replica_scale_attempt and not _is_gateway_ready_for_replica_scale_out(
            gateway_model
        ):
            return _ReplicaScalingResult(needs_more_replicas=True)
        configuration = gateways_services.get_gateway_configuration(gateway_model)
        used_nums = {
            r.replica_num for r in gateway_replicas if r.status != GatewayReplicaStatus.TERMINATED
        }
        new_nums = itertools.islice(get_lowest_unused_nums(used_nums), diff)
        new_gateway_compute_models = [
            gateways_services.create_gateway_compute_model(
                project_name=gateway_model.project.name,
                configuration=configuration,
                replica_num=replica_num,
                gateway_id=gateway_model.id,
                backend_id=gateway_model.backend_id,
            )
            for replica_num in new_nums
        ]
        logger.info(
            "%s: scaling out, adding %d replica(s)",
            fmt(gateway_model),
            diff,
        )
        new_attempt = (
            0 if reset_replica_scale_attempt else gateway_model.replica_scale_attempt
        ) + 1
        return _ReplicaScalingResult(
            new_gateway_compute_models=new_gateway_compute_models,
            gateway_update_map={
                "replica_scale_attempt": new_attempt,
                "last_replica_scale_attempt_at": NOW_PLACEHOLDER,
            },
            limit_reached=new_attempt >= _MAX_REPLICA_SCALE_ATTEMPTS,
            needs_more_replicas=True,
        )

    replicas_redundant = -diff
    active_replicas.sort(
        key=lambda r: (
            # Stop replicas with lower priority statuses first.
            REPLICA_SCALE_IN_PRIORITY.get(r.status, max(REPLICA_SCALE_IN_PRIORITY.values()) + 1),
            # Stop older replicas first. This allows to migrate off old instances
            # (e.g., to update the gateway to a new OS image).
            r.created_at,
        )
    )
    scale_in_replica_ids = [r.id for r in active_replicas[:replicas_redundant]]
    logger.info(
        "%s: scaling in, marking %d replica(s) for scale-in",
        fmt(gateway_model),
        len(scale_in_replica_ids),
    )
    result = _ReplicaScalingResult(scale_in_replica_ids=scale_in_replica_ids)
    if reset_replica_scale_attempt:
        result.gateway_update_map["replica_scale_attempt"] = 0
    return result


def _was_gateway_updated_since_last_scale_attempt(gateway_model: GatewayModel) -> bool:
    if gateway_model.last_update_at is None:
        return False
    if gateway_model.last_replica_scale_attempt_at is None:
        return True
    return gateway_model.last_update_at > gateway_model.last_replica_scale_attempt_at


_MAX_REPLICA_SCALE_ATTEMPTS = 15

# We use exponentially increasing retry delays so that a gateway with replicas
# that repeatedly fail to provision (e.g. due to no cloud capacity) does not
# retry constantly, recreating replicas forever.
_REPLICA_SCALE_RETRY_DELAYS = [
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=10),
    timedelta(minutes=30),
]


def _get_replica_scale_retry_delay(replica_scale_attempt: int) -> timedelta:
    index = replica_scale_attempt - 1
    if index < len(_REPLICA_SCALE_RETRY_DELAYS):
        return _REPLICA_SCALE_RETRY_DELAYS[index]
    return _REPLICA_SCALE_RETRY_DELAYS[-1]


def _is_gateway_ready_for_replica_scale_out(gateway_model: GatewayModel) -> bool:
    if gateway_model.replica_scale_attempt >= _MAX_REPLICA_SCALE_ATTEMPTS:
        return False
    if gateway_model.replica_scale_attempt == 0:
        return True
    retry_delay = _get_replica_scale_retry_delay(gateway_model.replica_scale_attempt)
    last_scale_attempt_at = gateway_model.last_replica_scale_attempt_at or gateway_model.created_at
    return get_current_datetime() - last_scale_attempt_at >= retry_delay


async def _apply_replica_scaling(
    session: AsyncSession,
    gateway_model: GatewayModel,
    scale_result: _ReplicaScalingResult,
) -> None:
    for gateway_compute_model in scale_result.new_gateway_compute_models:
        session.add(gateway_compute_model)
    if scale_result.scale_in_replica_ids:
        # The gateway pipeline does not need to lock gateway replicas — it only mutates `scale_in`,
        # which can only ever be flipped from False to True, so no races are expected.
        await session.execute(
            update(GatewayComputeModel)
            .where(GatewayComputeModel.id.in_(scale_result.scale_in_replica_ids))
            .values(scale_in=True)
        )
    if scale_result.limit_reached:
        events.emit(
            session,
            (
                f"Gateway made its {_MAX_REPLICA_SCALE_ATTEMPTS}th and final replica scale-out"
                " attempt. If it doesn't succeed, no further attempts will be made until the"
                " gateway is updated."
            ),
            actor=events.SystemActor(),
            targets=[events.Target.from_model(gateway_model)],
        )
