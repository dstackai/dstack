import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import InstrumentedAttribute, joinedload, load_only
from sqlalchemy.sql.base import ExecutableOption

from dstack._internal.core.backends.base.compute import ComputeWithGatewaySupport
from dstack._internal.core.errors import BackendError, BackendNotAvailable
from dstack._internal.core.models.gateways import GatewayReplicaStatus, GatewayStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
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
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import gateways as gateways_services
from dstack._internal.server.services.gateways import get_gateway_compute_configuration
from dstack._internal.server.services.gateways.pool import gateway_connections_pool
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GatewayReplicaPipelineItem(PipelineItem):
    status: GatewayReplicaStatus


class GatewayReplicaPipeline(Pipeline[GatewayReplicaPipelineItem]):
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
        self.__heartbeater = Heartbeater[GatewayReplicaPipelineItem](
            model_type=GatewayComputeModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = GatewayReplicaFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            GatewayReplicaWorker(
                queue=self._queue,
                heartbeater=self._heartbeater,
                pipeline_hinter=pipeline_hinter,
            )
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return GatewayComputeModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[GatewayReplicaPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[GatewayReplicaPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["GatewayReplicaWorker"]:
        return self.__workers


class GatewayReplicaFetcher(Fetcher[GatewayReplicaPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[GatewayReplicaPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[GatewayReplicaPipelineItem],
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

    @sentry_utils.instrument_pipeline_task("GatewayReplicaFetcher.fetch")
    async def fetch(self, limit: int) -> list[GatewayReplicaPipelineItem]:
        replica_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            GatewayComputeModel.__tablename__
        )
        async with replica_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(GatewayComputeModel)
                    .outerjoin(
                        GatewayModel,
                        or_(
                            GatewayModel.id == GatewayComputeModel.gateway_id,
                            GatewayModel.gateway_compute_id == GatewayComputeModel.id,
                        ),
                    )
                    .where(
                        GatewayComputeModel.deleted == False,
                        or_(
                            GatewayComputeModel.status.in_(
                                [
                                    GatewayReplicaStatus.SUBMITTED,
                                    GatewayReplicaStatus.PROVISIONING,
                                    GatewayReplicaStatus.TERMINATING,
                                ]
                            ),
                            and_(
                                GatewayComputeModel.status == GatewayReplicaStatus.RUNNING,
                                or_(
                                    GatewayModel.to_be_deleted == True,
                                    GatewayModel.status == GatewayStatus.FAILED,
                                    # Gateway was hard-deleted (unexpected, fetch to log an error)
                                    GatewayModel.id.is_(None),
                                ),
                            ),
                        ),
                        or_(
                            GatewayComputeModel.last_processed_at
                            <= now - self._min_processing_interval,
                            GatewayComputeModel.last_processed_at
                            == GatewayComputeModel.created_at,
                        ),
                        or_(
                            GatewayComputeModel.lock_expires_at.is_(None),
                            GatewayComputeModel.lock_expires_at < now,
                        ),
                        or_(
                            GatewayComputeModel.lock_owner.is_(None),
                            GatewayComputeModel.lock_owner == GatewayReplicaPipeline.__name__,
                        ),
                    )
                    .order_by(GatewayComputeModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=GatewayComputeModel)
                    .options(
                        load_only(
                            GatewayComputeModel.id,
                            GatewayComputeModel.lock_token,
                            GatewayComputeModel.lock_expires_at,
                            GatewayComputeModel.status,
                        )
                    )
                )
                replica_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for replica_model in replica_models:
                    prev_lock_expired = replica_model.lock_expires_at is not None
                    replica_model.lock_expires_at = lock_expires_at
                    replica_model.lock_token = lock_token
                    replica_model.lock_owner = GatewayReplicaPipeline.__name__
                    items.append(
                        GatewayReplicaPipelineItem(
                            __tablename__=GatewayComputeModel.__tablename__,
                            id=replica_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=replica_model.status,
                        )
                    )
                await session.commit()
        return items


class GatewayReplicaWorker(Worker[GatewayReplicaPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[GatewayReplicaPipelineItem],
        heartbeater: Heartbeater[GatewayReplicaPipelineItem],
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
            pipeline_hinter=pipeline_hinter,
        )

    @sentry_utils.instrument_pipeline_task("GatewayReplicaWorker.process")
    async def process(self, item: GatewayReplicaPipelineItem):
        if item.status == GatewayReplicaStatus.SUBMITTED:
            await _process_submitted_item(item)
        elif item.status == GatewayReplicaStatus.PROVISIONING:
            await _process_provisioning_item(item)
        elif item.status == GatewayReplicaStatus.RUNNING:
            await _process_running_item(item)
        elif item.status == GatewayReplicaStatus.TERMINATING:
            await _process_terminating_item(item)


class _GatewayReplicaUpdateMap(ItemUpdateMap, total=False):
    status: GatewayReplicaStatus
    status_message: Optional[str]
    active: bool
    deleted: bool
    instance_id: Optional[str]
    ip_address: Optional[str]
    region: Optional[str]
    hostname: Optional[str]
    backend_data: Optional[str]


_REPLICA_FIELDS_MIN: list[InstrumentedAttribute[Any]] = [
    GatewayComputeModel.id,
    GatewayComputeModel.lock_token,
    GatewayComputeModel.status,
    GatewayComputeModel.replica_num,
]

_GATEWAY_FIELDS_MIN: list[InstrumentedAttribute[Any]] = [
    GatewayModel.id,
    GatewayModel.name,
    GatewayModel.to_be_deleted,
    GatewayModel.status,
]


async def _load_gateway_replica(
    item: GatewayReplicaPipelineItem,
    replica_fields: list[InstrumentedAttribute[Any]],
    gateway_fields: list[InstrumentedAttribute[Any]],
    load_backends: bool = False,
    load_gateway_backend_type: bool = False,
) -> Optional[GatewayComputeModel]:
    def build_gateway_options(
        gateway_attr: InstrumentedAttribute[GatewayModel | None],
    ) -> list[ExecutableOption]:
        gateway_load = joinedload(gateway_attr).load_only(*gateway_fields)
        options: list[ExecutableOption] = [gateway_load]
        if load_backends:
            options.append(
                gateway_load.joinedload(GatewayModel.project).selectinload(ProjectModel.backends)
            )
        if load_gateway_backend_type:
            options.append(
                gateway_load.joinedload(GatewayModel.backend).load_only(BackendModel.type)
            )
        return options

    async with get_session_ctx() as session:
        stmt = (
            select(GatewayComputeModel)
            .where(
                GatewayComputeModel.id == item.id,
                GatewayComputeModel.lock_token == item.lock_token,
            )
            .options(
                load_only(*replica_fields),
                *build_gateway_options(GatewayComputeModel.gateway),
                *build_gateway_options(GatewayComputeModel.legacy_gateway),
            )
        )
        res = await session.execute(stmt)
        replica_model = res.unique().scalar_one_or_none()

    if replica_model is None:
        log_lock_token_mismatch(logger, item)
        return None
    return replica_model


def _get_loaded_gateway_model(replica_model: GatewayComputeModel) -> Optional[GatewayModel]:
    gateway_model = replica_model.gateway or replica_model.legacy_gateway
    if gateway_model is None:
        logger.error("Gateway replica %s is not attached to a gateway", replica_model.id)
    return gateway_model


def _mark_terminating_if_gateway_terminating(
    gateway_model: GatewayModel, replica_model: GatewayComputeModel
) -> Optional[_GatewayReplicaUpdateMap]:
    if gateway_model.to_be_deleted or gateway_model.status == GatewayStatus.FAILED:
        if replica_model.status == GatewayReplicaStatus.SUBMITTED:
            new_status = GatewayReplicaStatus.TERMINATED
            deleted = True
        else:
            new_status = GatewayReplicaStatus.TERMINATING
            deleted = False
        logger.info(
            "%s replica %d: marked %s, gateway is being deleted or failed",
            fmt(gateway_model),
            replica_model.replica_num,
            new_status.value,
        )
        return _GatewayReplicaUpdateMap(status=new_status, active=False, deleted=deleted)
    return None


async def _commit_update(
    item: GatewayReplicaPipelineItem,
    replica_model: GatewayComputeModel,
    update_map: _GatewayReplicaUpdateMap,
) -> None:
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)
    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(update_map, now=now)
        res = await session.execute(
            update(GatewayComputeModel)
            .where(
                GatewayComputeModel.id == replica_model.id,
                GatewayComputeModel.lock_token == replica_model.lock_token,
            )
            .values(**update_map)
            .returning(GatewayComputeModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)


async def _process_submitted_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN
        + [
            GatewayComputeModel.backend_id,
            GatewayComputeModel.configuration,
            GatewayComputeModel.ssh_public_key,
        ],
        gateway_fields=_GATEWAY_FIELDS_MIN
        + [
            GatewayModel.configuration,
            GatewayModel.region,
            GatewayModel.wildcard_domain,
        ],
        load_backends=True,
        load_gateway_backend_type=True,
    )
    if replica_model is None:
        return
    gateway_model = _get_loaded_gateway_model(replica_model)
    if gateway_model is None:
        await _commit_update(item, replica_model, update_map={})
        return
    if update_map := _mark_terminating_if_gateway_terminating(gateway_model, replica_model):
        await _commit_update(item, replica_model, update_map=update_map)
        return
    update_map = await _provision_gateway_replica(gateway_model, replica_model)
    await _commit_update(item, replica_model, update_map)


async def _provision_gateway_replica(
    gateway_model: GatewayModel,
    replica_model: GatewayComputeModel,
) -> _GatewayReplicaUpdateMap:
    try:
        if replica_model.backend_id is None:  # unexpected
            raise BackendNotAvailable()
        (_, backend) = await backends_services.get_project_backend_with_model_by_id_or_error(
            project=gateway_model.project, backend_id=replica_model.backend_id
        )
    except BackendNotAvailable:
        logger.warning(
            "%s replica %d: backend not available",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        return _GatewayReplicaUpdateMap(
            status=GatewayReplicaStatus.TERMINATED,
            active=False,
            deleted=True,
        )

    compute = backend.compute()
    assert isinstance(compute, ComputeWithGatewaySupport)
    compute_configuration = get_gateway_compute_configuration(replica_model, gateway_model)

    logger.debug(
        "%s replica %d: creating gateway compute",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    try:
        gpd = await run_async(compute.create_gateway, compute_configuration)
    except BackendError as e:
        status_message = f"Backend error: {repr(e)}"
        if len(e.args) > 0:
            status_message = str(e.args[0])
        logger.warning(
            "%s replica %d: failed to create gateway compute: %s",
            fmt(gateway_model),
            replica_model.replica_num,
            status_message,
        )
        return _GatewayReplicaUpdateMap(
            status=GatewayReplicaStatus.TERMINATED,
            status_message=status_message,
            active=False,
            deleted=True,
        )
    except Exception:
        logger.exception(
            "%s replica %d: unexpected error when creating gateway compute",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        return _GatewayReplicaUpdateMap(
            status=GatewayReplicaStatus.TERMINATED,
            status_message="Unexpected error",
            active=False,
            deleted=True,
        )

    logger.info(
        "%s replica %d: gateway compute created",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    return _GatewayReplicaUpdateMap(
        status=GatewayReplicaStatus.PROVISIONING,
        active=True,
        instance_id=gpd.instance_id,
        ip_address=gpd.ip_address,
        region=gpd.region,
        hostname=gpd.hostname,
        backend_data=gpd.backend_data,
    )


async def _process_provisioning_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN
        + [
            GatewayComputeModel.ip_address,
            GatewayComputeModel.ssh_private_key,
        ],
        gateway_fields=_GATEWAY_FIELDS_MIN,
    )
    if replica_model is None:
        return
    gateway_model = _get_loaded_gateway_model(replica_model)
    if gateway_model is None:
        await _commit_update(item, replica_model, update_map={})
        return
    if update_map := _mark_terminating_if_gateway_terminating(gateway_model, replica_model):
        await _commit_update(item, replica_model, update_map=update_map)
        return
    error = await _connect_and_configure_gateway_replica(gateway_model, replica_model)
    if error is None:
        logger.info(
            "%s replica %d: running",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        update_map = _GatewayReplicaUpdateMap(status=GatewayReplicaStatus.RUNNING, active=True)
    else:
        logger.warning(
            "%s replica %d: provisioning failed: %s",
            fmt(gateway_model),
            replica_model.replica_num,
            error,
        )
        update_map = _GatewayReplicaUpdateMap(
            status=GatewayReplicaStatus.TERMINATING, status_message=error, active=False
        )
    await _commit_update(item, replica_model, update_map)


async def _connect_and_configure_gateway_replica(
    gateway_model: GatewayModel,
    gateway_compute: GatewayComputeModel,
) -> Optional[str]:
    """Returns an error message on failure, None on success."""
    logger.debug(
        "%s replica %d: connecting to gateway compute",
        fmt(gateway_model),
        gateway_compute.replica_num,
    )
    # TODO: do only one connection/configuration attempt per pipeline tick.
    # Blocking on connect_to_gateway_with_retry and configure_gateway now has these cons:
    # - cannot terminate the gateway replica before it is provisioned because the DB model is locked
    # - connection retry counter is reset on server restart
    # - only one server replica is processing the gateway replica
    connection = await gateways_services.connect_to_gateway_with_retry(gateway_compute)
    if connection is None:
        logger.warning(
            "%s replica %d: failed to connect to gateway compute",
            fmt(gateway_model),
            gateway_compute.replica_num,
        )
        return "Failed to connect to gateway"
    try:
        await gateways_services.configure_gateway(connection)
    except Exception:
        logger.exception(
            "%s replica %d: failed to configure gateway",
            fmt(gateway_model),
            gateway_compute.replica_num,
        )
        return "Failed to configure gateway"
    logger.info(
        "%s replica %d: gateway compute connected and configured",
        fmt(gateway_model),
        gateway_compute.replica_num,
    )
    return None


async def _process_running_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN,
        gateway_fields=_GATEWAY_FIELDS_MIN,
    )
    if replica_model is None:
        return
    gateway_model = _get_loaded_gateway_model(replica_model)
    if gateway_model is None:
        await _commit_update(item, replica_model, update_map={})
        return
    if update_map := _mark_terminating_if_gateway_terminating(gateway_model, replica_model):
        await _commit_update(item, replica_model, update_map=update_map)
        return
    logger.warning(
        "%s replica %d: nothing to do in this pipeline tick",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    await _commit_update(item, replica_model, update_map={})


async def _process_terminating_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN
        + [
            GatewayComputeModel.instance_id,
            GatewayComputeModel.ip_address,
            GatewayComputeModel.backend_id,
            GatewayComputeModel.configuration,
            GatewayComputeModel.backend_data,
            GatewayComputeModel.ssh_public_key,
        ],
        gateway_fields=_GATEWAY_FIELDS_MIN
        + [
            GatewayModel.configuration,
            GatewayModel.region,
            GatewayModel.wildcard_domain,
        ],
        load_backends=True,
        load_gateway_backend_type=True,
    )
    if replica_model is None:
        return
    gateway_model = _get_loaded_gateway_model(replica_model)
    if gateway_model is None:
        await _commit_update(item, replica_model, update_map={})
        return
    mark_terminated_update_map = _GatewayReplicaUpdateMap(
        status=GatewayReplicaStatus.TERMINATED, active=False, deleted=True
    )
    try:
        if replica_model.backend_id is None:  # unexpected
            raise BackendNotAvailable()
        (_, backend) = await backends_services.get_project_backend_with_model_by_id_or_error(
            project=gateway_model.project,
            backend_id=replica_model.backend_id,
        )
    except BackendNotAvailable:
        logger.error(
            "%s replica %d: backend not available, cannot terminate. Marking TERMINATED without termination",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        await _commit_update(item, replica_model, mark_terminated_update_map)
        return
    compute = backend.compute()
    assert isinstance(compute, ComputeWithGatewaySupport)
    compute_configuration = get_gateway_compute_configuration(replica_model, gateway_model)
    if replica_model.instance_id is None:
        logger.warning(
            "%s replica %d: instance_id is None, skipping gateway replica termination",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        await _commit_update(item, replica_model, mark_terminated_update_map)
        return

    logger.debug(
        "%s replica %d: terminating gateway compute",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    try:
        await run_async(
            compute.terminate_gateway,
            replica_model.instance_id,
            compute_configuration,
            replica_model.backend_data,
        )
    except Exception:
        logger.exception(
            "%s replica %d: error when terminating gateway compute",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        await _commit_update(item, replica_model, update_map={})
        return

    logger.info(
        "%s replica %d: gateway compute terminated",
        fmt(gateway_model),
        replica_model.replica_num,
    )

    if replica_model.ip_address is not None:
        await gateway_connections_pool.remove(replica_model.ip_address)

    await _commit_update(item, replica_model, mark_terminated_update_map)
