import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional, Sequence

from httpx import HTTPStatusError
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, joinedload, load_only, with_loader_criteria
from sqlalchemy.sql.base import ExecutableOption

from dstack._internal.core.backends.base.compute import (
    ComputeWithGatewayLoadBalancerSupport,
    ComputeWithGatewaySupport,
)
from dstack._internal.core.errors import BackendError, BackendNotAvailable, GatewayError
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.models.gateways import GatewayReplicaStatus, GatewayStatus
from dstack._internal.core.models.runs import JobSpec, JobStatus, RunStatus, ServiceSpec
from dstack._internal.proxy.gateway.schemas.services import ServiceListItem
from dstack._internal.server import settings
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
    GatewayModel,
    GatewayReplicaModel,
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    ServiceRegistrationModel,
    ServiceReplicaRegistrationModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import events
from dstack._internal.server.services import gateways as gateways_services
from dstack._internal.server.services.gateways import (
    get_gateway_configuration,
    get_gateway_lb_configuration,
    get_gateway_replica_configuration,
)
from dstack._internal.server.services.gateways.client import GatewayClient
from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.services.gateways.pool import gateway_connections_pool
from dstack._internal.server.services.instances import get_instance_remote_connection_info
from dstack._internal.server.services.jobs import job_model_to_job_submission
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.services.runs import get_run_spec
from dstack._internal.server.services.services import (
    get_gateway_https,
    should_configure_service_https_on_gateway,
)
from dstack._internal.server.utils import tracing
from dstack._internal.utils.common import get_current_datetime, get_or_error, run_async
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
            model_type=GatewayReplicaModel,
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
        return GatewayReplicaModel.__name__

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

    @tracing.instrument_pipeline_task("GatewayReplicaFetcher.fetch")
    async def fetch(self, limit: int) -> list[GatewayReplicaPipelineItem]:
        replica_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            GatewayReplicaModel.__tablename__
        )
        async with replica_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(GatewayReplicaModel)
                    .outerjoin(
                        GatewayModel,
                        or_(
                            GatewayModel.id == GatewayReplicaModel.gateway_id,
                            GatewayModel.gateway_replica_id == GatewayReplicaModel.id,
                        ),
                    )
                    .where(
                        GatewayReplicaModel.deleted == False,
                        or_(
                            GatewayReplicaModel.status.in_(
                                [
                                    GatewayReplicaStatus.SUBMITTED,
                                    GatewayReplicaStatus.PROVISIONING,
                                    GatewayReplicaStatus.RUNNING,
                                    GatewayReplicaStatus.TERMINATING,
                                ]
                            ),
                        ),
                        or_(
                            GatewayReplicaModel.last_processed_at
                            <= now - self._min_processing_interval,
                            GatewayReplicaModel.last_processed_at
                            == GatewayReplicaModel.created_at,
                        ),
                        or_(
                            GatewayReplicaModel.lock_expires_at.is_(None),
                            GatewayReplicaModel.lock_expires_at < now,
                        ),
                        or_(
                            GatewayReplicaModel.lock_owner.is_(None),
                            GatewayReplicaModel.lock_owner == GatewayReplicaPipeline.__name__,
                        ),
                    )
                    .order_by(GatewayReplicaModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=GatewayReplicaModel)
                    .options(
                        load_only(
                            GatewayReplicaModel.id,
                            GatewayReplicaModel.lock_token,
                            GatewayReplicaModel.lock_expires_at,
                            GatewayReplicaModel.status,
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
                            __tablename__=GatewayReplicaModel.__tablename__,
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

    @tracing.instrument_pipeline_task("GatewayReplicaWorker.process")
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
    backend_data: Optional[str]


_REPLICA_FIELDS_MIN: list[InstrumentedAttribute[Any]] = [
    GatewayReplicaModel.id,
    GatewayReplicaModel.lock_token,
    GatewayReplicaModel.status,
    GatewayReplicaModel.replica_num,
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
) -> Optional[GatewayReplicaModel]:
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
            select(GatewayReplicaModel)
            .where(
                GatewayReplicaModel.id == item.id,
                GatewayReplicaModel.lock_token == item.lock_token,
            )
            .options(
                load_only(*replica_fields),
                *build_gateway_options(GatewayReplicaModel.gateway),
                *build_gateway_options(GatewayReplicaModel.legacy_gateway),
            )
        )
        res = await session.execute(stmt)
        replica_model = res.unique().scalar_one_or_none()

    if replica_model is None:
        log_lock_token_mismatch(logger, item)
        return None
    return replica_model


def _get_loaded_gateway_model(replica_model: GatewayReplicaModel) -> Optional[GatewayModel]:
    gateway_model = replica_model.gateway or replica_model.legacy_gateway
    if gateway_model is None:
        logger.error("Gateway replica %s is not attached to a gateway", replica_model.id)
    return gateway_model


def _mark_terminating_if_needed(
    gateway_model: GatewayModel, replica_model: GatewayReplicaModel
) -> Optional[_GatewayReplicaUpdateMap]:
    if gateway_model.to_be_deleted or gateway_model.status == GatewayStatus.FAILED:
        status_message = None
    elif replica_model.scale_in:
        status_message = "Scaled in"
    else:
        return
    if replica_model.status == GatewayReplicaStatus.SUBMITTED:
        new_status = GatewayReplicaStatus.TERMINATED
        deleted = True
    else:
        new_status = GatewayReplicaStatus.TERMINATING
        deleted = False
    logger.info(
        "%s replica %d: marked %s (%s)",
        fmt(gateway_model),
        replica_model.replica_num,
        new_status.value,
        status_message or "-",
    )
    update_map = _GatewayReplicaUpdateMap(status=new_status, active=False, deleted=deleted)
    if status_message:
        update_map["status_message"] = status_message
    return update_map


# TODO: Consider refactoring the pipeline for consistency with other pipelines - split into process
# and apply phases instead of calling the `_commit_update()` helper from everywhere
async def _commit_update(
    item: GatewayReplicaPipelineItem,
    replica_model: GatewayReplicaModel,
    update_map: _GatewayReplicaUpdateMap,
) -> None:
    async with get_session_ctx() as session:
        await _apply_update(session, item, replica_model, update_map)


async def _apply_update(
    session: AsyncSession,
    item: GatewayReplicaPipelineItem,
    replica_model: GatewayReplicaModel,
    update_map: _GatewayReplicaUpdateMap,
) -> bool:
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)
    now = get_current_datetime()
    resolve_now_placeholders(update_map, now=now)
    res = await session.execute(
        update(GatewayReplicaModel)
        .where(
            GatewayReplicaModel.id == replica_model.id,
            GatewayReplicaModel.lock_token == replica_model.lock_token,
        )
        .values(**update_map)
        .returning(GatewayReplicaModel.id)
    )
    updated_ids = list(res.scalars().all())
    if len(updated_ids) == 0:
        log_lock_token_changed_after_processing(logger, item)
        return False
    if update_map.get("deleted"):
        await session.execute(
            delete(ServiceRegistrationModel).where(
                ServiceRegistrationModel.gateway_replica_id == replica_model.id
            )
        )
        await session.execute(
            delete(ServiceReplicaRegistrationModel).where(
                ServiceReplicaRegistrationModel.gateway_replica_id == replica_model.id
            )
        )
    return True


async def _process_submitted_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN
        + [
            GatewayReplicaModel.backend_id,
            GatewayReplicaModel.configuration,
            GatewayReplicaModel.ssh_public_key,
            GatewayReplicaModel.scale_in,
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
    if update_map := _mark_terminating_if_needed(gateway_model, replica_model):
        await _commit_update(item, replica_model, update_map=update_map)
        return
    update_map = await _provision_gateway_replica(gateway_model, replica_model)
    await _commit_update(item, replica_model, update_map)


async def _provision_gateway_replica(
    gateway_model: GatewayModel,
    replica_model: GatewayReplicaModel,
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
    replica_configuration = get_gateway_replica_configuration(replica_model, gateway_model)

    logger.debug(
        "%s replica %d: creating gateway replica",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    try:
        gpd = await run_async(compute.create_gateway_replica, replica_configuration)
    except BackendError as e:
        status_message = f"Backend error: {repr(e)}"
        if len(e.args) > 0:
            status_message = str(e.args[0])
        logger.warning(
            "%s replica %d: failed to create gateway replica: %s",
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
            "%s replica %d: unexpected error when creating gateway replica",
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
        "%s replica %d: gateway replica created",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    return _GatewayReplicaUpdateMap(
        status=GatewayReplicaStatus.PROVISIONING,
        active=True,
        instance_id=gpd.instance_id,
        ip_address=gpd.ip_address,
        region=gpd.region,
        backend_data=gpd.backend_data,
    )


async def _process_provisioning_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN
        + [
            GatewayReplicaModel.ip_address,
            GatewayReplicaModel.ssh_private_key,
            GatewayReplicaModel.scale_in,
            GatewayReplicaModel.instance_id,
            GatewayReplicaModel.backend_id,
            GatewayReplicaModel.configuration,
        ],
        gateway_fields=_GATEWAY_FIELDS_MIN
        + [
            GatewayModel.configuration,
            GatewayModel.region,
            GatewayModel.wildcard_domain,
            GatewayModel.hostname,
            GatewayModel.backend_data,
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
    if update_map := _mark_terminating_if_needed(gateway_model, replica_model):
        await _commit_update(item, replica_model, update_map=update_map)
        return
    if _is_legacy_aws_acm_gateway_with_pending_migration(gateway_model):
        await _commit_update(item, replica_model, update_map={})
        return
    error = await _connect_and_configure_gateway_replica(gateway_model, replica_model)
    if error is not None:
        logger.warning(
            "%s replica %d: provisioning failed: %s",
            fmt(gateway_model),
            replica_model.replica_num,
            error,
        )
        await _commit_update(
            item,
            replica_model,
            _GatewayReplicaUpdateMap(
                status=GatewayReplicaStatus.TERMINATING, status_message=error, active=False
            ),
        )
        return

    if gateway_model.hostname is not None:
        reg_error = await _register_replica_with_load_balancer(gateway_model, replica_model)
        if reg_error is not None:
            logger.warning(
                "%s replica %d: failed to register with load balancer: %s",
                fmt(gateway_model),
                replica_model.replica_num,
                reg_error,
            )
            await _commit_update(
                item,
                replica_model,
                _GatewayReplicaUpdateMap(
                    status=GatewayReplicaStatus.TERMINATING,
                    status_message=reg_error,
                    active=False,
                ),
            )
            return

    logger.info("%s replica %d: running", fmt(gateway_model), replica_model.replica_num)
    await _commit_update(
        item,
        replica_model,
        _GatewayReplicaUpdateMap(status=GatewayReplicaStatus.RUNNING, active=True),
    )


async def _register_replica_with_load_balancer(
    gateway_model: GatewayModel,
    replica_model: GatewayReplicaModel,
) -> Optional[str]:
    """Registers the replica instance with the gateway's load balancer.
    Returns an error message on failure, None on success.
    """
    if replica_model.instance_id is None:
        return "instance_id is None, cannot register with load balancer"
    try:
        if replica_model.backend_id is None:
            raise BackendNotAvailable()
        (_, backend) = await backends_services.get_project_backend_with_model_by_id_or_error(
            project=gateway_model.project, backend_id=replica_model.backend_id
        )
    except BackendNotAvailable:
        return "Backend not available"
    compute = backend.compute()
    if not isinstance(compute, ComputeWithGatewayLoadBalancerSupport):
        return "Backend does not support load balancer operations"
    lb_configuration = get_gateway_lb_configuration(gateway_model)
    try:
        await run_async(
            compute.register_gateway_replica_with_load_balancer,
            replica_model.instance_id,
            lb_configuration,
            gateway_model.backend_data,
        )
    except Exception:
        logger.exception(
            "%s replica %d: error registering with load balancer",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        return "Error registering with load balancer"
    logger.info(
        "%s replica %d: registered with load balancer",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    return None


async def _connect_and_configure_gateway_replica(
    gateway_model: GatewayModel,
    gateway_replica: GatewayReplicaModel,
) -> Optional[str]:
    """Returns an error message on failure, None on success."""
    logger.debug(
        "%s replica %d: connecting to gateway replica",
        fmt(gateway_model),
        gateway_replica.replica_num,
    )
    # TODO: do only one connection/configuration attempt per pipeline tick.
    # Blocking on connect_to_gateway_replica_with_retry and configure_gateway_replica now has
    # these cons:
    # - cannot terminate the gateway replica before it is provisioned because the DB model is locked
    # - connection retry counter is reset on server restart
    # - only one server replica is processing the gateway replica
    connection = await gateways_services.connect_to_gateway_replica_with_retry(gateway_replica)
    if connection is None:
        logger.warning(
            "%s replica %d: failed to connect to gateway replica",
            fmt(gateway_model),
            gateway_replica.replica_num,
        )
        return "Failed to connect to gateway replica"
    try:
        await gateways_services.configure_gateway_replica(connection)
    except Exception:
        logger.exception(
            "%s replica %d: failed to configure gateway replica",
            fmt(gateway_model),
            gateway_replica.replica_num,
        )
        return "Failed to configure gateway replica"
    logger.info(
        "%s replica %d: gateway replica connected and configured",
        fmt(gateway_model),
        gateway_replica.replica_num,
    )
    return None


async def _process_running_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN
        + [
            GatewayReplicaModel.scale_in,
            GatewayReplicaModel.ip_address,
            GatewayReplicaModel.ssh_private_key,
        ],
        gateway_fields=_GATEWAY_FIELDS_MIN
        + [
            GatewayModel.project_id,
            GatewayModel.configuration,
            GatewayModel.region,
            GatewayModel.wildcard_domain,
        ],
        load_gateway_backend_type=True,
    )
    if replica_model is None:
        return
    gateway_model = _get_loaded_gateway_model(replica_model)
    if gateway_model is None:
        await _commit_update(item, replica_model, update_map={})
        return
    if update_map := _mark_terminating_if_needed(gateway_model, replica_model):
        await _commit_update(item, replica_model, update_map=update_map)
        return
    try:
        connection = await gateway_connections_pool.get_or_add(
            hostname=get_or_error(replica_model.ip_address),
            id_rsa=replica_model.ssh_private_key,
        )
    except Exception as e:
        logger.warning(
            "%s replica %d: failed to connect to gateway: %s",
            fmt(gateway_model),
            replica_model.replica_num,
            e,
        )
        await _commit_update(item, replica_model, update_map={})
        return
    async with connection.client() as client:
        try:
            currently_registered_services = await client.list_services()
        except Exception as e:
            if isinstance(e, HTTPStatusError) and e.response.status_code == 404:
                logger.warning(
                    (
                        "%s replica %d: got error 404 when listing services, which indicates a"
                        " pre-0.21.0 gateway. Skipping state sync until the gateway is updated"
                    ),
                    fmt(gateway_model),
                    replica_model.replica_num,
                )
            else:
                logger.warning(
                    "%s replica %d: failed to list services: %r",
                    fmt(gateway_model),
                    replica_model.replica_num,
                    e,
                )
            await _commit_update(item, replica_model, update_map={})
            return
    stmt = (
        select(RunModel)
        .where(
            RunModel.gateway_id == gateway_model.id,
            RunModel.deleted == False,
            RunModel.status.not_in(RunStatus.finished_statuses() + [RunStatus.TERMINATING]),
        )
        .options(
            load_only(RunModel.id),
            joinedload(RunModel.jobs).load_only(JobModel.id),
            with_loader_criteria(
                JobModel,
                and_(
                    JobModel.status == JobStatus.RUNNING,
                    JobModel.registered == True,
                ),
            ),
        )
    )
    async with get_session_ctx() as session:
        res = await session.execute(stmt)
        expected_runs = res.scalars().unique().all()
        plan = _plan_state_sync(
            currently_registered=currently_registered_services,
            expected=expected_runs,
        )
        run_models_by_id, job_models_by_id = await _load_runs_and_jobs_for_state_sync(
            session, plan
        )

    sync_result = await _perform_state_sync(
        connection, gateway_model, replica_model, run_models_by_id, job_models_by_id, plan
    )

    async with get_session_ctx() as session:
        if not await _apply_update(session, item, replica_model, update_map={}):
            return
        reconcile_records_result = await _reconcile_registration_records(
            session, replica_model, currently_registered_services, sync_result
        )
        await _emit_state_sync_events(
            session,
            gateway_model,
            replica_model,
            run_models_by_id,
            job_models_by_id,
            sync_result,
            reconcile_records_result,
        )


async def _perform_state_sync(
    connection: GatewayConnection,
    gateway_model: GatewayModel,
    replica_model: GatewayReplicaModel,
    run_models_by_id: dict[uuid.UUID, RunModel],
    job_models_by_id: dict[uuid.UUID, JobModel],
    plan: "_StateSyncPlan",
) -> "_StateSyncResult":
    result = _StateSyncResult()
    for service_ref, run_id in plan.set_run_ids.items():
        logger.debug(
            "%s replica %d: setting id %s for service %s/%s",
            fmt(gateway_model),
            replica_model.replica_num,
            run_id,
            service_ref.project_name,
            service_ref.run_name,
        )
        try:
            async with connection.client() as client:
                await client.set_service_id(
                    project=service_ref.project_name,
                    run_name=service_ref.run_name,
                    run_id=run_id,
                )
        except Exception:
            logger.exception(
                "%s replica %d: failed to set id %s for service %s/%s",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
                service_ref.project_name,
                service_ref.run_name,
            )
            continue
        logger.info(
            "%s replica %d: id %s set for service %s/%s",
            fmt(gateway_model),
            replica_model.replica_num,
            run_id,
            service_ref.project_name,
            service_ref.run_name,
        )
    for service_ref in plan.unregister_services:
        logger.debug(
            "%s replica %d: unregistering service %s/%s",
            fmt(gateway_model),
            replica_model.replica_num,
            service_ref.project_name,
            service_ref.run_name,
        )
        try:
            async with connection.client() as client:
                await client.unregister_service(
                    project=service_ref.project_name,
                    run_name=service_ref.run_name,
                )
        except GatewayError as e:
            if service_ref.id is not None:
                result.failed_service_unregistrations[service_ref.id] = e.msg
            else:
                logger.warning(
                    "%s replica %d: failed to unregister legacy service %s/%s with unknown ID: %s",
                    fmt(gateway_model),
                    replica_model.replica_num,
                    service_ref.project_name,
                    service_ref.run_name,
                    e.msg,
                )
            continue
        except Exception:
            logger.exception(
                "%s replica %d: failed to unregister service %s/%s",
                fmt(gateway_model),
                replica_model.replica_num,
                service_ref.project_name,
                service_ref.run_name,
            )
            if service_ref.id is not None:
                result.failed_service_unregistrations[service_ref.id] = "Unexpected error"
            continue
        if service_ref.id is not None:
            result.unregistered_services.add(service_ref.id)
        else:
            logger.warning(
                "%s replica %d: unregistered legacy service %s/%s with unknown ID",
                fmt(gateway_model),
                replica_model.replica_num,
                service_ref.project_name,
                service_ref.run_name,
            )
        # Service replicas implicitly unregistered along with the service
        result.unregistered_replicas.update(plan.unregister_replicas.get(service_ref, set()))
    for service_ref, replica_ids in plan.unregister_replicas.items():
        if service_ref.id in result.unregistered_services:
            continue  # already unregistered along with the service
        for replica_id in replica_ids:
            logger.debug(
                "%s replica %d: unregistering replica %s for service %s/%s",
                fmt(gateway_model),
                replica_model.replica_num,
                replica_id,
                service_ref.project_name,
                service_ref.run_name,
            )
            try:
                async with connection.client() as client:
                    await client.unregister_replica(
                        project=service_ref.project_name,
                        run_name=service_ref.run_name,
                        job_id=replica_id,
                    )
            except GatewayError as e:
                result.failed_replica_unregistrations[replica_id] = e.msg
                continue
            except Exception:
                logger.exception(
                    "%s replica %d: failed to unregister replica %s for service %s/%s",
                    fmt(gateway_model),
                    replica_model.replica_num,
                    replica_id,
                    service_ref.project_name,
                    service_ref.run_name,
                )
                result.failed_replica_unregistrations[replica_id] = "Unexpected error"
                continue
            result.unregistered_replicas.add(replica_id)
    for run_id in plan.register_services:
        run_model = run_models_by_id.get(run_id)
        if run_model is None:
            error_message = "Run not found"
            logger.error(
                "%s replica %d: run %s not found, cannot register service",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
            )
            result.failed_service_registrations[run_id] = error_message
            continue
        try:
            async with connection.client() as client:
                await _register_service(client, gateway_model, replica_model, run_model)
        except GatewayError as e:
            result.failed_service_registrations[run_id] = e.msg
            continue
        except Exception:
            logger.exception(
                "%s replica %d: failed to register service for run %s",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
            )
            result.failed_service_registrations[run_id] = "Unexpected error"
            continue
        result.registered_services.add(run_id)
    for run_id, replica_ids in plan.register_replicas.items():
        if run_id in result.failed_service_registrations:
            continue
        run_model = run_models_by_id.get(run_id)
        if run_model is None:
            logger.error(
                "%s replica %d: run %s not found, cannot register replicas",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
            )
            for replica_id in replica_ids:
                result.failed_replica_registrations[replica_id] = "Run not found"
            continue
        for replica_id in replica_ids:
            job_model = job_models_by_id.get(replica_id)
            if job_model is None:
                logger.error(
                    "%s replica %d: job %s not found, cannot register replica",
                    fmt(gateway_model),
                    replica_model.replica_num,
                    replica_id,
                )
                result.failed_replica_registrations[replica_id] = "Job not found"
                continue
            try:
                async with connection.client() as client:
                    await _register_replica(
                        client, gateway_model, replica_model, run_model, job_model
                    )
            except GatewayError as e:
                result.failed_replica_registrations[replica_id] = e.msg
                continue
            except Exception:
                logger.exception(
                    "%s replica %d: failed to register replica %s",
                    fmt(gateway_model),
                    replica_model.replica_num,
                    replica_id,
                )
                result.failed_replica_registrations[replica_id] = "Unexpected error"
                continue
            result.registered_replicas.add(replica_id)
    return result


def _get_or_create_service_registration(
    session: AsyncSession,
    existing_by_id: dict[uuid.UUID, ServiceRegistrationModel],
    run_id: uuid.UUID,
    gateway_replica_id: uuid.UUID,
) -> ServiceRegistrationModel:
    if registration := existing_by_id.get(run_id):
        return registration
    registration = ServiceRegistrationModel(
        run_id=run_id,
        gateway_replica_id=gateway_replica_id,
        register_attempt=0,
        register_status_message=None,
        unregister_attempt=0,
        unregister_status_message=None,
    )
    session.add(registration)
    return registration


def _get_or_create_service_replica_registration(
    session: AsyncSession,
    existing_by_id: dict[uuid.UUID, ServiceReplicaRegistrationModel],
    job_id: uuid.UUID,
    gateway_replica_id: uuid.UUID,
) -> ServiceReplicaRegistrationModel:
    if registration := existing_by_id.get(job_id):
        return registration
    registration = ServiceReplicaRegistrationModel(
        job_id=job_id,
        gateway_replica_id=gateway_replica_id,
        register_attempt=0,
        register_status_message=None,
        unregister_attempt=0,
        unregister_status_message=None,
    )
    session.add(registration)
    return registration


@dataclass
class _ReconcileRegistrationRecordsResult:
    services_with_new_registration_error: set[uuid.UUID] = field(default_factory=set)
    replicas_with_new_registration_error: set[uuid.UUID] = field(default_factory=set)
    services_with_new_unregistration_error: set[uuid.UUID] = field(default_factory=set)
    replicas_with_new_unregistration_error: set[uuid.UUID] = field(default_factory=set)


async def _reconcile_registration_records(
    session: AsyncSession,
    replica_model: GatewayReplicaModel,
    initially_registered: list[ServiceListItem],
    sync_result: "_StateSyncResult",
) -> _ReconcileRegistrationRecordsResult:
    result = _ReconcileRegistrationRecordsResult()
    initially_registered_run_ids = {
        uuid.UUID(s.id) for s in initially_registered if s.id is not None
    }
    initially_registered_replica_ids = {
        uuid.UUID(r.id) for s in initially_registered for r in s.replicas
    }
    registered_run_ids = (
        initially_registered_run_ids - sync_result.unregistered_services
    ) | sync_result.registered_services
    registered_replica_ids = (
        initially_registered_replica_ids - sync_result.unregistered_replicas
    ) | sync_result.registered_replicas

    keep_run_ids = registered_run_ids | sync_result.failed_service_registrations.keys()
    keep_replica_ids = registered_replica_ids | sync_result.failed_replica_registrations.keys()

    await session.execute(
        delete(ServiceRegistrationModel).where(
            ServiceRegistrationModel.gateway_replica_id == replica_model.id,
            ServiceRegistrationModel.run_id.not_in(keep_run_ids),
        )
    )
    await session.execute(
        delete(ServiceReplicaRegistrationModel).where(
            ServiceReplicaRegistrationModel.gateway_replica_id == replica_model.id,
            ServiceReplicaRegistrationModel.job_id.not_in(keep_replica_ids),
        )
    )

    service_registrations_by_run_id: dict[uuid.UUID, ServiceRegistrationModel] = {}
    if keep_run_ids:
        res = await session.execute(
            select(ServiceRegistrationModel).where(
                ServiceRegistrationModel.gateway_replica_id == replica_model.id,
            )
        )
        service_registrations_by_run_id = {r.run_id: r for r in res.scalars().all()}
    replica_registrations_by_job_id: dict[uuid.UUID, ServiceReplicaRegistrationModel] = {}
    if keep_replica_ids:
        res = await session.execute(
            select(ServiceReplicaRegistrationModel).where(
                ServiceReplicaRegistrationModel.gateway_replica_id == replica_model.id,
            )
        )
        replica_registrations_by_job_id = {r.job_id: r for r in res.scalars().all()}

    for run_id in registered_run_ids:
        registration = _get_or_create_service_registration(
            session=session,
            existing_by_id=service_registrations_by_run_id,
            run_id=run_id,
            gateway_replica_id=replica_model.id,
        )
        registration.is_registered = True
        registration.register_attempt = 0
        registration.register_status_message = None
        unregister_error_message = sync_result.failed_service_unregistrations.get(run_id)
        if unregister_error_message is None:
            registration.unregister_attempt = 0
            registration.unregister_status_message = None
        else:
            registration.unregister_attempt += 1
            if unregister_error_message != registration.unregister_status_message:
                registration.unregister_status_message = unregister_error_message
                result.services_with_new_unregistration_error.add(run_id)
    for job_id in registered_replica_ids:
        registration = _get_or_create_service_replica_registration(
            session=session,
            existing_by_id=replica_registrations_by_job_id,
            job_id=job_id,
            gateway_replica_id=replica_model.id,
        )
        registration.is_registered = True
        registration.register_attempt = 0
        registration.register_status_message = None
        unregister_error_message = sync_result.failed_replica_unregistrations.get(job_id)
        if unregister_error_message is None:
            registration.unregister_attempt = 0
            registration.unregister_status_message = None
        else:
            registration.unregister_attempt += 1
            if unregister_error_message != registration.unregister_status_message:
                registration.unregister_status_message = unregister_error_message
                result.replicas_with_new_unregistration_error.add(job_id)
    for run_id, error_message in sync_result.failed_service_registrations.items():
        registration = _get_or_create_service_registration(
            session=session,
            existing_by_id=service_registrations_by_run_id,
            run_id=run_id,
            gateway_replica_id=replica_model.id,
        )
        registration.is_registered = False
        registration.register_attempt += 1
        if error_message != registration.register_status_message:
            registration.register_status_message = error_message
            result.services_with_new_registration_error.add(run_id)
    for job_id, error_message in sync_result.failed_replica_registrations.items():
        registration = _get_or_create_service_replica_registration(
            session=session,
            existing_by_id=replica_registrations_by_job_id,
            job_id=job_id,
            gateway_replica_id=replica_model.id,
        )
        registration.is_registered = False
        registration.register_attempt += 1
        if error_message != registration.register_status_message:
            registration.register_status_message = error_message
            result.replicas_with_new_registration_error.add(job_id)
    return result


async def _emit_state_sync_events(
    session,
    gateway_model: GatewayModel,
    replica_model: GatewayReplicaModel,
    run_models_by_id: dict[uuid.UUID, RunModel],
    job_models_by_id: dict[uuid.UUID, JobModel],
    sync_result: "_StateSyncResult",
    reconcile_records_result: _ReconcileRegistrationRecordsResult,
) -> None:
    # TODO: once gateway replica event targets are supported, link events to gateway replicas
    # instead of gateways, and remove gateway replica nums from messages.
    for run_id in sync_result.unregistered_services:
        run_model = run_models_by_id.get(run_id)
        if run_model is None:
            logger.error(
                "%s replica %d: run %s not found, cannot emit service unregistration event",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
            )
            continue
        events.emit(
            session,
            f"Service unregistered from gateway replica {replica_model.replica_num}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(run_model), events.Target.from_model(gateway_model)],
        )
    for job_id in sync_result.unregistered_replicas:
        job_model = job_models_by_id.get(job_id)
        if job_model is None:
            logger.error(
                "%s replica %d: job %s not found, cannot emit replica unregistration event",
                fmt(gateway_model),
                replica_model.replica_num,
                job_id,
            )
            continue
        events.emit(
            session,
            f"Service replica unregistered from gateway replica {replica_model.replica_num}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model), events.Target.from_model(gateway_model)],
        )
    for run_id in sync_result.registered_services:
        run_model = run_models_by_id.get(run_id)
        if run_model is None:
            logger.error(
                "%s replica %d: run %s not found, cannot emit service registration event",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
            )
            continue
        events.emit(
            session,
            f"Service registered on gateway replica {replica_model.replica_num}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(run_model), events.Target.from_model(gateway_model)],
        )
    for job_id in sync_result.registered_replicas:
        job_model = job_models_by_id.get(job_id)
        if job_model is None:
            logger.error(
                "%s replica %d: job %s not found, cannot emit replica registration event",
                fmt(gateway_model),
                replica_model.replica_num,
                job_id,
            )
            continue
        events.emit(
            session,
            f"Service replica registered on gateway replica {replica_model.replica_num}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model), events.Target.from_model(gateway_model)],
        )
    for run_id, error_message in sync_result.failed_service_registrations.items():
        if run_id not in reconcile_records_result.services_with_new_registration_error:
            continue  # same error as before, do not emit duplicate event
        run_model = run_models_by_id.get(run_id)
        if run_model is None:
            logger.error(
                "%s replica %d: run %s not found, cannot emit service registration event",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
            )
            continue
        events.emit(
            session,
            f"Encountered service registration error on gateway replica {replica_model.replica_num}: {error_message}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(run_model), events.Target.from_model(gateway_model)],
        )
    for job_id, error_message in sync_result.failed_replica_registrations.items():
        if job_id not in reconcile_records_result.replicas_with_new_registration_error:
            continue  # same error as before, do not emit duplicate event
        job_model = job_models_by_id.get(job_id)
        if job_model is None:
            logger.error(
                "%s replica %d: job %s not found, cannot emit replica registration event",
                fmt(gateway_model),
                replica_model.replica_num,
                job_id,
            )
            continue
        events.emit(
            session,
            f"Encountered service replica registration error on gateway replica {replica_model.replica_num}: {error_message}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model), events.Target.from_model(gateway_model)],
        )
    for run_id, error_message in sync_result.failed_service_unregistrations.items():
        if run_id not in reconcile_records_result.services_with_new_unregistration_error:
            continue  # same error as before, do not emit duplicate event
        run_model = run_models_by_id.get(run_id)
        if run_model is None:
            logger.error(
                "%s replica %d: run %s not found, cannot emit service unregistration event",
                fmt(gateway_model),
                replica_model.replica_num,
                run_id,
            )
            continue
        events.emit(
            session,
            f"Encountered service unregistration error on gateway replica {replica_model.replica_num}: {error_message}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(run_model), events.Target.from_model(gateway_model)],
        )
    for job_id, error_message in sync_result.failed_replica_unregistrations.items():
        if job_id not in reconcile_records_result.replicas_with_new_unregistration_error:
            continue  # same error as before, do not emit duplicate event
        job_model = job_models_by_id.get(job_id)
        if job_model is None:
            logger.error(
                "%s replica %d: job %s not found, cannot emit replica unregistration event",
                fmt(gateway_model),
                replica_model.replica_num,
                job_id,
            )
            continue
        events.emit(
            session,
            f"Encountered service replica unregistration error on gateway replica {replica_model.replica_num}: {error_message}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model), events.Target.from_model(gateway_model)],
        )


async def _load_runs_and_jobs_for_state_sync(
    session: AsyncSession,
    plan: "_StateSyncPlan",
) -> tuple[dict[uuid.UUID, RunModel], dict[uuid.UUID, JobModel]]:
    run_ids = (
        plan.register_services
        | plan.register_replicas.keys()
        | {s.id for s in plan.unregister_services if s.id is not None}
    )
    run_models_by_id: dict[uuid.UUID, RunModel] = {}
    if run_ids:
        res = await session.execute(
            select(RunModel).where(RunModel.id.in_(run_ids)).options(joinedload(RunModel.project))
        )
        run_models_by_id = {run.id: run for run in res.unique().scalars().all()}

    job_ids: set[uuid.UUID] = set()
    for replica_ids in plan.register_replicas.values():
        job_ids |= replica_ids
    for replica_ids in plan.unregister_replicas.values():
        job_ids |= replica_ids
    job_models_by_id: dict[uuid.UUID, JobModel] = {}
    if job_ids:
        res = await session.execute(
            select(JobModel)
            .where(JobModel.id.in_(job_ids))
            .options(
                joinedload(JobModel.instance).joinedload(InstanceModel.project),
                joinedload(JobModel.project).load_only(ProjectModel.id, ProjectModel.name),
            )
        )
        job_models_by_id = {job.id: job for job in res.unique().scalars().all()}

    return run_models_by_id, job_models_by_id


async def _register_service(
    client: GatewayClient,
    gateway_model: GatewayModel,
    replica_model: GatewayReplicaModel,
    run_model: RunModel,
) -> None:
    run_spec = get_run_spec(run_model)
    if run_spec.configuration.type != "service":
        message = f"Run {run_model.id} is not a service, cannot register"
        logger.error("%s replica %d: %s", fmt(gateway_model), replica_model.replica_num, message)
        raise RuntimeError(message)
    if run_model.service_spec is None:
        message = f"Run {run_model.id} has no service spec, cannot register"
        logger.error("%s replica %d: %s", fmt(gateway_model), replica_model.replica_num, message)
        raise RuntimeError(message)
    service_spec = validate_json_extra_ignore(ServiceSpec, run_model.service_spec)
    domain = service_spec.get_domain()
    if domain is None:
        message = f"Run {run_model.id} service spec has no domain, cannot register"
        logger.error("%s replica %d: %s", fmt(gateway_model), replica_model.replica_num, message)
        raise RuntimeError(message)

    gateway_configuration = get_gateway_configuration(gateway_model)
    has_replica_group_router = any(
        g.router is not None for g in run_spec.configuration.replica_groups
    )
    logger.debug(
        "%s replica %d: registering service %s/%s",
        fmt(gateway_model),
        replica_model.replica_num,
        run_model.project.name,
        run_model.run_name,
    )
    await client.register_service(
        project=run_model.project.name,
        run_id=run_model.id,
        run_name=run_model.run_name,
        domain=domain,
        service_https=should_configure_service_https_on_gateway(run_spec, gateway_configuration),
        gateway_https=get_gateway_https(gateway_configuration),
        auth=run_spec.configuration.auth,
        client_max_body_size=settings.DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE,
        options=service_spec.options,
        rate_limits=run_spec.configuration.rate_limits,
        ssh_private_key=run_model.project.ssh_private_key,
        has_router_replica=has_replica_group_router,
    )


async def _register_replica(
    client: GatewayClient,
    gateway_model: GatewayModel,
    replica_model: GatewayReplicaModel,
    run_model: RunModel,
    job_model: JobModel,
) -> None:
    run_spec = get_run_spec(run_model)
    if run_spec.configuration.type != "service":
        message = f"Run {run_model.id} is not a service, cannot register replica"
        logger.error("%s replica %d: %s", fmt(gateway_model), replica_model.replica_num, message)
        raise RuntimeError(message)
    instance = job_model.instance
    if instance is None:
        message = f"Job {job_model.id} has no instance, cannot register replica"
        logger.error("%s replica %d: %s", fmt(gateway_model), replica_model.replica_num, message)
        raise RuntimeError(message)
    job_spec = validate_json_extra_ignore(JobSpec, job_model.job_spec_data)
    job_submission = job_model_to_job_submission(job_model)

    instance_project_ssh_private_key = None
    if job_model.project_id != instance.project_id:
        instance_project_ssh_private_key = instance.project.ssh_private_key
    ssh_head_proxy = None
    ssh_head_proxy_private_key = None
    rci = get_instance_remote_connection_info(instance)
    if rci is not None and rci.ssh_proxy is not None:
        ssh_head_proxy = rci.ssh_proxy
        ssh_head_proxy_private_key = get_or_error(rci.ssh_proxy_keys)[0].private

    logger.debug(
        "%s replica %d: registering replica %s for service %s/%s",
        fmt(gateway_model),
        replica_model.replica_num,
        job_model.id,
        run_model.project.name,
        run_model.run_name,
    )
    await client.register_replica(
        project=run_model.project.name,
        run_name=run_model.run_name,
        configuration=run_spec.configuration,
        job_spec=job_spec,
        job_submission=job_submission,
        instance_project_ssh_private_key=instance_project_ssh_private_key,
        ssh_head_proxy=ssh_head_proxy,
        ssh_head_proxy_private_key=ssh_head_proxy_private_key,
    )


@dataclass(frozen=True)
class _ServiceRef:
    id: uuid.UUID | None
    project_name: str
    run_name: str


@dataclass
class _StateSyncPlan:
    register_services: set[uuid.UUID] = field(default_factory=set)
    unregister_services: set[_ServiceRef] = field(default_factory=set)
    # run ID -> set[job ID]
    register_replicas: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    unregister_replicas: dict[_ServiceRef, set[uuid.UUID]] = field(default_factory=dict)
    set_run_ids: dict[_ServiceRef, uuid.UUID] = field(default_factory=dict)


@dataclass
class _StateSyncResult:
    registered_services: set[uuid.UUID] = field(default_factory=set)
    registered_replicas: set[uuid.UUID] = field(default_factory=set)
    unregistered_services: set[uuid.UUID] = field(default_factory=set)
    unregistered_replicas: set[uuid.UUID] = field(default_factory=set)

    # run ID -> error message
    failed_service_registrations: dict[uuid.UUID, str] = field(default_factory=dict)
    failed_replica_registrations: dict[uuid.UUID, str] = field(default_factory=dict)
    failed_service_unregistrations: dict[uuid.UUID, str] = field(default_factory=dict)
    failed_replica_unregistrations: dict[uuid.UUID, str] = field(default_factory=dict)


def _plan_state_sync(
    currently_registered: list[ServiceListItem], expected: Sequence[RunModel]
) -> _StateSyncPlan:
    plan = _StateSyncPlan()
    expected_run_id_to_run = {run.id: run for run in expected}
    expected_job_id_to_run = {job.id: run for run in expected for job in run.jobs}
    expected_run_ids = {run.id for run in expected}
    currently_registered_run_ids: set[uuid.UUID] = set()

    for service in currently_registered:
        service_ref = _ServiceRef(
            id=uuid.UUID(service.id) if service.id is not None else None,
            project_name=service.project_name,
            run_name=service.run_name,
        )
        if service.id is not None:
            run_id = uuid.UUID(service.id)
        else:
            # Try to recover ID for legacy pre-0.21.0 service
            for replica in service.replicas:
                if run := expected_job_id_to_run.get(uuid.UUID(replica.id)):
                    run_id = run.id
                    plan.set_run_ids[service_ref] = run_id
                    break
            else:
                # Could not recover ID, and none of the current replicas are relevant - unregister.
                # If the service is relevant, we'll re-register it with ID.
                plan.unregister_services.add(service_ref)
                continue
        currently_registered_run_ids.add(run_id)
        if run := expected_run_id_to_run.get(run_id):
            currently_registered_job_ids = {uuid.UUID(replica.id) for replica in service.replicas}
            expected_job_ids = {job.id for job in run.jobs}
            plan.register_replicas[run.id] = expected_job_ids - currently_registered_job_ids
            plan.unregister_replicas[service_ref] = currently_registered_job_ids - expected_job_ids
        else:
            plan.unregister_services.add(service_ref)
            plan.unregister_replicas[service_ref] = {
                uuid.UUID(replica.id) for replica in service.replicas
            }

    for run_id in expected_run_ids - currently_registered_run_ids:
        plan.register_services.add(run_id)
        plan.register_replicas[run_id] = {job.id for job in expected_run_id_to_run[run_id].jobs}

    return plan


async def _process_terminating_item(item: GatewayReplicaPipelineItem):
    replica_model = await _load_gateway_replica(
        item,
        replica_fields=_REPLICA_FIELDS_MIN
        + [
            GatewayReplicaModel.instance_id,
            GatewayReplicaModel.ip_address,
            GatewayReplicaModel.backend_id,
            GatewayReplicaModel.configuration,
            GatewayReplicaModel.backend_data,
            GatewayReplicaModel.ssh_public_key,
        ],
        gateway_fields=_GATEWAY_FIELDS_MIN
        + [
            GatewayModel.configuration,
            GatewayModel.region,
            GatewayModel.wildcard_domain,
            GatewayModel.hostname,
            GatewayModel.backend_data,
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
    replica_configuration = get_gateway_replica_configuration(replica_model, gateway_model)
    if replica_model.instance_id is None:
        logger.warning(
            "%s replica %d: instance_id is None, skipping gateway replica termination",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        await _commit_update(item, replica_model, mark_terminated_update_map)
        return
    if _is_legacy_aws_acm_gateway_with_pending_migration(gateway_model):
        await _commit_update(item, replica_model, update_map={})
        return

    if gateway_model.hostname is not None:
        await _deregister_gateway_replica_from_load_balancer(compute, gateway_model, replica_model)

    logger.debug(
        "%s replica %d: terminating gateway replica",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    try:
        await run_async(
            compute.terminate_gateway_replica,
            replica_model.instance_id,
            replica_configuration,
            replica_model.backend_data,
        )
    except Exception:
        logger.exception(
            "%s replica %d: error when terminating gateway replica",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        await _commit_update(item, replica_model, update_map={})
        return

    logger.info(
        "%s replica %d: gateway replica terminated",
        fmt(gateway_model),
        replica_model.replica_num,
    )

    if replica_model.ip_address is not None:
        await gateway_connections_pool.remove(replica_model.ip_address)

    await _commit_update(item, replica_model, mark_terminated_update_map)


async def _deregister_gateway_replica_from_load_balancer(
    compute: ComputeWithGatewaySupport,
    gateway_model: GatewayModel,
    replica_model: GatewayReplicaModel,
) -> None:
    if not isinstance(compute, ComputeWithGatewayLoadBalancerSupport):
        logger.error(
            (
                "%s replica %d: cannot deregister from load balancer,"
                " backend does not support load balancer operations"
            ),
            fmt(gateway_model),
            replica_model.replica_num,
        )
        return
    if replica_model.instance_id is None:
        logger.error(
            "%s replica %d: cannot deregister from load balancer, instance_id is None",
            fmt(gateway_model),
            replica_model.replica_num,
        )
        return
    logger.debug(
        "%s replica %d: deregistering from load balancer",
        fmt(gateway_model),
        replica_model.replica_num,
    )
    try:
        await run_async(
            compute.deregister_gateway_replica_from_load_balancer,
            replica_model.instance_id,
            get_gateway_lb_configuration(gateway_model),
            gateway_model.backend_data,
        )
        logger.info(
            "%s replica %d: deregistered from load balancer",
            fmt(gateway_model),
            replica_model.replica_num,
        )
    except Exception:
        logger.exception(
            (
                "%s replica %d: error deregistering from load balancer."
                " Proceeding with gateway replica termination,"
                " relying on automatic deregistration by the load balancer"
            ),
            fmt(gateway_model),
            replica_model.replica_num,
        )


def _is_legacy_aws_acm_gateway_with_pending_migration(gateway_model: GatewayModel) -> bool:
    """
    If `True`, the gateway cannot be used for replica (de)register operations until the migration
    completes, since its `backend_data` does not yet have the relevant load balancer details.
    """
    configuration = get_gateway_configuration(gateway_model)
    if (
        configuration.certificate is not None
        and configuration.certificate.type == "acm"
        and gateway_model.hostname is None
    ):
        logger.warning(
            "Found AWS ACM gateway %s without a hostname, which should indicate a pre-0.21.0"
            " gateway not yet migrated to the 0.21.0 format. Waiting for the gateway pipeline to"
            " perform the migration",
            gateway_model.id,
        )
        return True
    return False
