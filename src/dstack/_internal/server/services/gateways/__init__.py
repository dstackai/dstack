import asyncio
import datetime
import itertools
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import partial
from typing import List, Optional, Sequence

import httpx
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

import dstack._internal.utils.random_names as random_names
from dstack._internal.core.backends.base.compute import (
    get_dstack_gateway_wheel,
    get_dstack_runner_version,
)
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_GATEWAY_SUPPORT,
    BACKENDS_WITH_PRIVATE_GATEWAY_SUPPORT,
)
from dstack._internal.core.errors import (
    GatewayError,
    ResourceNotExistsError,
    ServerClientError,
    SSHError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ApplyAction, EntityReference
from dstack._internal.core.models.gateways import (
    GATEWAY_REPLICAS_DEFAULT,
    AnyGatewayRouterConfig,
    ApplyGatewayPlanInput,
    Gateway,
    GatewayComputeConfiguration,
    GatewayConfiguration,
    GatewayPlan,
    GatewayReplica,
    GatewayReplicaStatus,
    GatewaySpec,
    GatewayStatus,
    LetsEncryptGatewayCertificate,
)
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.core.services.diff import (
    ModelDiff,
    diff_models,
    format_diff_fields_for_event,
)
from dstack._internal.proxy.gateway.const import SERVICE_SCALING_WINDOWS
from dstack._internal.proxy.gateway.schemas.stats import PerWindowStats, Stat
from dstack._internal.server import settings
from dstack._internal.server.db import get_db, is_db_postgres, is_db_sqlite
from dstack._internal.server.models import (
    BackendModel,
    ExportedGatewayModel,
    GatewayComputeModel,
    GatewayModel,
    ImportModel,
    ProjectModel,
    UserModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.backends import (
    check_backend_type_available,
    get_project_backend_with_model_by_type_or_error,
)
from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.services.gateways.pool import gateway_connections_pool
from dstack._internal.server.services.locking import (
    advisory_lock_ctx,
    get_locker,
    string_to_lock_id,
)
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.services.plugins import apply_plugin_policies
from dstack._internal.server.utils.common import gather_map_async
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils.common import (
    get_current_datetime,
    get_or_error,
    interpolate_gateway_domain,
)
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
_CONF_UPDATABLE_FIELDS = frozenset({"domain"})
if FeatureFlags.GATEWAY_SCALING:
    _CONF_UPDATABLE_FIELDS |= {"replicas"}


def switch_gateway_status(
    session: AsyncSession,
    gateway_model: GatewayModel,
    new_status: GatewayStatus,
    actor: events.AnyActor = events.SystemActor(),
):
    old_status = gateway_model.status
    if old_status == new_status:
        return

    gateway_model.status = new_status
    emit_gateway_status_change_event(
        session=session,
        gateway_model=gateway_model,
        old_status=old_status,
        new_status=new_status,
        status_message=gateway_model.status_message,
        actor=actor,
    )


def emit_gateway_status_change_event(
    session: AsyncSession,
    gateway_model: GatewayModel,
    old_status: GatewayStatus,
    new_status: GatewayStatus,
    status_message: Optional[str],
    actor: events.AnyActor = events.SystemActor(),
) -> None:
    if old_status == new_status:
        return
    msg = get_gateway_status_change_message(
        old_status=old_status,
        new_status=new_status,
        status_message=status_message,
    )
    events.emit(session, msg, actor=actor, targets=[events.Target.from_model(gateway_model)])


def get_gateway_status_change_message(
    old_status: GatewayStatus, new_status: GatewayStatus, status_message: Optional[str]
) -> str:
    msg = f"Gateway status changed {old_status.upper()} -> {new_status.upper()}"
    if status_message is not None:
        msg += f" ({status_message})"
    return msg


GATEWAY_CONNECT_ATTEMPTS = 30
GATEWAY_CONNECT_DELAY = 10
GATEWAY_CONFIGURE_ATTEMPTS = 50
GATEWAY_CONFIGURE_DELAY = 3
# Artificial limit to avoid doing too many per-replica operations (gateway replica provisioning,
# service registration, etc) in a single pipeline tick. Can be lifted once the implementation is
# more mature.
GATEWAY_MAX_REPLICAS = 3  # documented in gateways.md, keep in sync


async def list_project_gateways(
    session: AsyncSession,
    project: ProjectModel,
    include_imported: bool = False,
) -> List[Gateway]:
    gateways = await list_project_gateway_models(
        session=session,
        project=project,
        include_imported=include_imported,
        load_gateway_compute=True,
        load_backend_type=True,
    )
    return [
        gateway_model_to_gateway(g, default_gateway_id=project.default_gateway_id)
        for g in gateways
    ]


async def get_gateway_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[Gateway]:
    gateway = await get_project_gateway_model_by_reference(
        session=session,
        project=project,
        ref=EntityReference(name=name, project=None),
        load_gateway_compute=True,
        load_backend_type=True,
    )
    if gateway is None:
        return None
    return gateway_model_to_gateway(gateway, default_gateway_id=project.default_gateway_id)


def create_gateway_compute_model(
    project_name: str,
    configuration: GatewayConfiguration,
    replica_num: int,
    gateway_id: uuid.UUID,
    backend_id: uuid.UUID,
) -> GatewayComputeModel:
    assert configuration.name is not None

    private_bytes, public_bytes = generate_rsa_key_pair_bytes()
    gateway_ssh_private_key = private_bytes.decode()
    gateway_ssh_public_key = public_bytes.decode()

    compute_configuration = GatewayComputeConfiguration(
        project_name=project_name,
        instance_name=f"{configuration.name}-{replica_num}",
        backend=configuration.backend,
        region=configuration.region,
        instance_type=configuration.instance_type,
        public_ip=configuration.public_ip,
        ssh_key_pub=gateway_ssh_public_key,
        certificate=configuration.certificate,
        tags=configuration.tags,
        router=configuration.router,
    )

    now = get_current_datetime()
    return GatewayComputeModel(
        gateway_id=gateway_id,
        backend_id=backend_id,
        replica_num=replica_num,
        configuration=compute_configuration.json(),
        ssh_private_key=gateway_ssh_private_key,
        ssh_public_key=gateway_ssh_public_key,
        status=GatewayReplicaStatus.SUBMITTED,
        active=False,
        created_at=now,
        last_processed_at=now,
    )


async def create_gateway(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    configuration: GatewayConfiguration,
    pipeline_hinter: PipelineHinterProtocol,
    *,
    effective_configuration: Optional[GatewayConfiguration] = None,
) -> Gateway:
    if effective_configuration is None:
        spec = await apply_plugin_policies(
            user=user.name,
            project=project.name,
            spec=GatewaySpec(configuration=configuration),
        )
        effective_configuration = spec.configuration
        _validate_gateway_configuration(effective_configuration)
    configuration = effective_configuration

    backend_model, _ = await get_project_backend_with_model_by_type_or_error(
        project=project, backend_type=configuration.backend
    )

    lock_namespace = f"gateway_names_{project.name}"
    if is_db_sqlite():
        # Start new transaction to see committed changes after lock
        await session.commit()
    elif is_db_postgres():
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )
    lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)
    async with lock:
        if configuration.name is None:
            configuration.name = await generate_gateway_name(session=session, project=project)

        now = get_current_datetime()
        gateway = GatewayModel(
            id=uuid.uuid4(),
            name=configuration.name,
            region=configuration.region,
            project_id=project.id,
            backend_id=backend_model.id,
            wildcard_domain=configuration.domain,
            configuration=configuration.json(),
            status=GatewayStatus.SUBMITTED,
            desired_replica_count=(
                configuration.replicas
                if configuration.replicas is not None
                else GATEWAY_REPLICAS_DEFAULT
            ),
            created_at=now,
            last_processed_at=now,
        )
        session.add(gateway)
        events.emit(
            session,
            f"Gateway created. Status: {gateway.status.upper()}",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(gateway)],
        )
        await session.commit()

        default_gateway = await get_project_default_gateway_model(session=session, project=project)
        if default_gateway is None or configuration.default:
            await set_default_gateway(
                session=session,
                project=project,
                ref=EntityReference(name=configuration.name, project=None),
                user=user,
            )
            default_gateway = gateway
        pipeline_hinter.hint_fetch(GatewayModel.__name__)
        gateway = await get_project_gateway_model_by_reference(
            session=session,
            project=project,
            ref=EntityReference(name=configuration.name, project=None),
            load_gateway_compute=True,
            load_backend_type=True,
        )
        assert gateway is not None
        return gateway_model_to_gateway(gateway, default_gateway_id=default_gateway.id)


async def connect_to_gateway_with_retry(
    gateway_compute: GatewayComputeModel,
) -> Optional[GatewayConnection]:
    """
    Create gateway connection and add it to connection pool.
    Give gateway sufficient time to become available. In the case of gateway
    being accessed via domain (e.g. Kubernetes LB), it may take some time before
    the domain can be resolved.
    """

    if gateway_compute.ip_address is None:
        logger.warning("Gateway replica %s has no ip_address, cannot connect", gateway_compute.id)
        return None

    connection = None

    for attempt in range(GATEWAY_CONNECT_ATTEMPTS):
        try:
            connection = await gateway_connections_pool.get_or_add(
                gateway_compute.ip_address, gateway_compute.ssh_private_key
            )
            break
        except SSHError as e:
            if attempt < GATEWAY_CONNECT_ATTEMPTS - 1:
                logger.debug("Failed to connect to gateway %s: %s", gateway_compute.ip_address, e)
                await asyncio.sleep(GATEWAY_CONNECT_DELAY)
            else:
                logger.error("Failed to connect to gateway %s: %s", gateway_compute.ip_address, e)

    return connection


async def delete_gateways(
    session: AsyncSession,
    project: ProjectModel,
    gateways_names: List[str],
    user: UserModel,
):
    res = await session.execute(
        select(GatewayModel).where(
            GatewayModel.project_id == project.id,
            GatewayModel.name.in_(gateways_names),
        )
    )
    gateway_models = res.scalars().all()
    gateways_ids = sorted([g.id for g in gateway_models])
    await session.commit()
    logger.info("Deleting gateways: %s", [g.name for g in gateway_models])
    async with get_locker(get_db().dialect_name).lock_ctx(
        GatewayModel.__tablename__, gateways_ids
    ):
        # Retry locking gateways to increase lock acquisition chances.
        # This hack is needed until requests are queued.
        gateway_models = []
        for i in range(10):
            res = await session.execute(
                select(GatewayModel)
                .where(
                    GatewayModel.id.in_(gateways_ids),
                    GatewayModel.project_id == project.id,
                    GatewayModel.lock_expires_at.is_(None),
                )
                .options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
                .order_by(GatewayModel.id)  # take locks in order
                .with_for_update(key_share=True, of=GatewayModel)
                .execution_options(populate_existing=True)
            )
            gateway_models = res.scalars().all()
            if len(gateway_models) == len(gateways_ids):
                break
            await asyncio.sleep(0.5)
        if len(gateway_models) != len(gateways_ids):
            # TODO: Make the endpoint fully async so we don't need to lock and error.
            raise ServerClientError(
                "Failed to delete gateways: gateways are being processed currently. Try again later."
            )
        for gateway_model in gateway_models:
            if not gateway_model.to_be_deleted:
                gateway_model.to_be_deleted = True
                events.emit(
                    session,
                    "Gateway marked for deletion",
                    actor=events.UserActor.from_user(user),
                    targets=[events.Target.from_model(gateway_model)],
                )
        await session.commit()


async def set_gateway_wildcard_domain(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    wildcard_domain: Optional[str],
    user: UserModel,
) -> Gateway:
    async with get_project_gateway_model_by_name_for_update(
        session=session, project=project, name=name
    ) as gateway:
        if gateway is None:
            raise ResourceNotExistsError()
        old_domain = gateway.wildcard_domain
        if old_domain != wildcard_domain:
            gateway.wildcard_domain = wildcard_domain
            if gateway.configuration is not None:
                conf = get_gateway_configuration(gateway)
                conf.domain = wildcard_domain
                gateway.configuration = conf.json()
            events.emit(
                session,
                f"Gateway wildcard domain changed {old_domain!r} -> {gateway.wildcard_domain!r}",
                actor=events.UserActor.from_user(user),
                targets=[events.Target.from_model(gateway)],
            )
            await session.commit()
    return gateway_model_to_gateway(gateway, default_gateway_id=project.default_gateway_id)


async def set_default_gateway(
    session: AsyncSession, project: ProjectModel, ref: EntityReference, user: Optional[UserModel]
):
    gateway = await get_project_gateway_model_by_reference(
        session=session, project=project, ref=ref
    )
    if gateway is None:
        raise ResourceNotExistsError()
    if gateway.to_be_deleted:
        raise ServerClientError("Cannot set gateway marked for deletion as default")
    previous_gateway = await get_project_default_gateway_model(session, project)
    if previous_gateway is not None and previous_gateway.id == gateway.id:
        return
    await session.execute(
        update(ProjectModel)
        .where(
            ProjectModel.id == project.id,
        )
        .values(
            default_gateway_id=gateway.id,
        )
    )
    if previous_gateway is not None:
        events.emit(
            session,
            "Gateway unset as project default",
            actor=events.UserActor.from_user(user) if user is not None else events.SystemActor(),
            targets=[
                events.Target.from_model(previous_gateway),
                events.Target.from_model(project),
            ],
        )
    events.emit(
        session,
        "Gateway set as project default",
        actor=events.UserActor.from_user(user) if user is not None else events.SystemActor(),
        targets=[
            events.Target.from_model(gateway),
            events.Target.from_model(project),
        ],
    )
    await session.commit()


async def list_project_gateway_models(
    session: AsyncSession,
    project: ProjectModel,
    include_imported: bool = False,
    load_gateway_compute: bool = False,
    load_backend_type: bool = False,
) -> Sequence[GatewayModel]:
    stmt = select(GatewayModel)
    if include_imported:
        stmt = stmt.where(
            or_(
                GatewayModel.project_id == project.id,
                exists().where(
                    ImportModel.project_id == project.id,
                    ImportModel.export_id == ExportedGatewayModel.export_id,
                    ExportedGatewayModel.gateway_id == GatewayModel.id,
                ),
            )
        ).options(joinedload(GatewayModel.project).load_only(ProjectModel.id, ProjectModel.name))
    else:
        stmt = stmt.where(GatewayModel.project_id == project.id)
    if load_gateway_compute:
        stmt = stmt.options(
            joinedload(GatewayModel.gateway_compute)
            .joinedload(GatewayComputeModel.backend)
            .load_only(BackendModel.type)
        )
        stmt = stmt.options(
            selectinload(GatewayModel.gateway_computes)
            .joinedload(GatewayComputeModel.backend)
            .load_only(BackendModel.type)
        )
    if load_backend_type:
        stmt = stmt.options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
    res = await session.execute(stmt)
    return res.unique().scalars().all()


async def get_project_gateway_model_by_reference(
    session: AsyncSession,
    project: ProjectModel,
    ref: EntityReference,
    load_gateway_compute: bool = False,
    load_backend_type: bool = False,
) -> Optional[GatewayModel]:
    stmt = select(GatewayModel).where(GatewayModel.name == ref.name)
    if ref.project is None or ref.project == project.name:
        stmt = stmt.where(GatewayModel.project_id == project.id)
    else:
        stmt = stmt.where(
            exists().where(
                ImportModel.project_id == project.id,
                ImportModel.export_id == ExportedGatewayModel.export_id,
                ExportedGatewayModel.gateway_id == GatewayModel.id,
                GatewayModel.project_id == ProjectModel.id,
                ProjectModel.name == ref.project,
            )
        )
    if load_gateway_compute:
        stmt = stmt.options(
            joinedload(GatewayModel.gateway_compute)
            .joinedload(GatewayComputeModel.backend)
            .load_only(BackendModel.type)
        )
        stmt = stmt.options(
            selectinload(GatewayModel.gateway_computes)
            .joinedload(GatewayComputeModel.backend)
            .load_only(BackendModel.type)
        )
    if load_backend_type:
        stmt = stmt.options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
    res = await session.execute(stmt)
    return res.scalar()


@asynccontextmanager
async def get_project_gateway_model_by_name_for_update(
    session: AsyncSession, project: ProjectModel, name: str
) -> AsyncGenerator[Optional[GatewayModel], None]:
    """
    Fetch the gateway from the database and lock it for update.

    **NOTE**: commit changes to the database before exiting from this context manager,
              so that in-memory locks are only released after commit.
    """

    filters = [
        GatewayModel.project_id == project.id,
        GatewayModel.name == name,
    ]
    res = await session.execute(select(GatewayModel.id).where(*filters))
    gateway_id = res.scalar_one_or_none()
    if gateway_id is None:
        yield None
    else:
        async with get_locker(get_db().dialect_name).lock_ctx(
            GatewayModel.__tablename__, [gateway_id]
        ):
            # Refetch after lock
            res = await session.execute(
                select(GatewayModel)
                .where(GatewayModel.id.in_([gateway_id]), *filters)
                .options(
                    joinedload(GatewayModel.gateway_compute)
                    .joinedload(GatewayComputeModel.backend)
                    .load_only(BackendModel.type)
                )
                .options(
                    selectinload(GatewayModel.gateway_computes)
                    .joinedload(GatewayComputeModel.backend)
                    .load_only(BackendModel.type)
                )
                .options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
                .with_for_update(key_share=True, of=GatewayModel)
            )
            yield res.scalar_one_or_none()


async def get_project_default_gateway_model(
    session: AsyncSession,
    project: ProjectModel,
    load_gateway_compute: bool = False,
    load_backend_type: bool = False,
) -> Optional[GatewayModel]:
    stmt = select(GatewayModel).where(
        GatewayModel.id == project.default_gateway_id,
        GatewayModel.to_be_deleted == False,
        or_(
            GatewayModel.project_id == project.id,
            exists().where(
                ImportModel.project_id == project.id,
                ImportModel.export_id == ExportedGatewayModel.export_id,
                ExportedGatewayModel.gateway_id == GatewayModel.id,
            ),
        ),
    )
    if load_gateway_compute:
        stmt = stmt.options(
            joinedload(GatewayModel.gateway_compute)
            .joinedload(GatewayComputeModel.backend)
            .load_only(BackendModel.type)
        )
        stmt = stmt.options(
            selectinload(GatewayModel.gateway_computes)
            .joinedload(GatewayComputeModel.backend)
            .load_only(BackendModel.type)
        )
    if load_backend_type:
        stmt = stmt.options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def generate_gateway_name(session: AsyncSession, project: ProjectModel) -> str:
    gateways = await list_project_gateway_models(session=session, project=project)
    names = {g.name for g in gateways}
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


# TODO: Connect to gateway outside session
async def get_or_add_gateway_connections(
    session: AsyncSession, gateway_id: uuid.UUID
) -> tuple[GatewayModel, List[GatewayConnection]]:
    res = await session.execute(
        select(GatewayModel)
        .where(GatewayModel.id == gateway_id)
        .options(joinedload(GatewayModel.gateway_compute))
        .options(selectinload(GatewayModel.gateway_computes))
    )
    gateway = res.scalar_one_or_none()
    if gateway is None:
        raise GatewayError("Gateway not found")
    computes = get_gateway_compute_models(gateway)
    if not computes:
        raise GatewayError("Gateway compute not found")
    connections: List[GatewayConnection] = []
    for compute in computes:
        if compute.ip_address is None:
            logger.warning("Gateway replica %s has no ip_address", compute.id)
            raise GatewayError("Failed to connect to gateway")
        try:
            conn = await gateway_connections_pool.get_or_add(
                hostname=compute.ip_address,
                id_rsa=compute.ssh_private_key,
            )
            connections.append(conn)
        except Exception as e:
            logger.warning("Failed to connect to gateway %s: %s", compute.ip_address, e)
            raise GatewayError("Failed to connect to gateway")
    return gateway, connections


async def get_combined_gateway_stats(
    session: AsyncSession,
    gateway_id: uuid.UUID,
    project_name: str,
    run_name: str,
) -> Optional[PerWindowStats]:
    """
    Return stats for *run_name* aggregated across all replicas of *gateway_id*.
    """
    try:
        _, connections = await get_or_add_gateway_connections(session, gateway_id)
    except GatewayError:
        return None
    per_replica: list[PerWindowStats] = []
    for conn in connections:
        stats = await conn.get_stats(project_name, run_name)
        if stats is None:  # Stats not fetched yet
            # TODO: find a way to make service scaling decisions even if some gateway replicas are
            # unavailable for fetching stats.
            return None
        per_replica.append(stats)
    return _merge_per_window_stats(per_replica) if per_replica else None


def _merge_per_window_stats(stats_per_gateway_replica: list[PerWindowStats]) -> PerWindowStats:
    merged: PerWindowStats = {}
    for window in SERVICE_SCALING_WINDOWS:
        total_requests = 0
        total_time_of_all_requests = 0.0
        for gateway_replica_stats in stats_per_gateway_replica:
            stat = gateway_replica_stats[window]
            total_requests += stat.requests
            total_time_of_all_requests += stat.requests * stat.request_time
        merged[window] = Stat(
            requests=total_requests,
            request_time=(total_time_of_all_requests / total_requests if total_requests else 0.0),
        )
    return merged


async def init_gateways(session: AsyncSession):
    res = await session.execute(
        select(GatewayComputeModel).where(
            GatewayComputeModel.status == GatewayReplicaStatus.RUNNING,
            GatewayComputeModel.active == True,
            GatewayComputeModel.deleted == False,
        )
    )
    gateway_computes = res.scalars().all()

    if len(gateway_computes) > 0:
        logger.info(f"Connecting to {len(gateway_computes)} gateways...", {"show_path": False})

    async with advisory_lock_ctx(
        bind=session,
        dialect_name=get_db().dialect_name,
        resource="gateway_tunnels",
    ):
        for gateway, error in await gather_map_async(
            [g for g in gateway_computes if g.ip_address],
            lambda g: gateway_connections_pool.get_or_add(
                get_or_error(g.ip_address), g.ssh_private_key, True
            ),
            return_exceptions=True,
        ):
            if isinstance(error, Exception):
                logger.warning("Failed to connect to gateway %s: %s", gateway.ip_address, error)

        if settings.SKIP_GATEWAY_UPDATE:
            logger.debug("Skipping gateways update due to DSTACK_SKIP_GATEWAY_UPDATE env variable")
        else:
            build = get_dstack_runner_version() or "latest"

            for gateway_compute, res in await gather_map_async(
                gateway_computes,
                lambda c: _update_gateway(c, build),
                return_exceptions=True,
            ):
                if isinstance(res, Exception):
                    logger.warning(
                        "Failed to update gateway %s: %s", gateway_compute.ip_address, res
                    )
                elif isinstance(res, bool) and res:
                    gateway_compute.app_updated_at = get_current_datetime()

        for gateway_compute, error in await gather_map_async(
            await gateway_connections_pool.all(),
            # Need several attempts to handle short gateway downtime after update
            partial(configure_gateway, attempts=7),
            return_exceptions=True,
        ):
            if isinstance(error, Exception):
                logger.warning(
                    "Failed to configure gateway %s: %r", gateway_compute.ip_address, error
                )


async def _update_gateway(gateway_compute_model: GatewayComputeModel, build: str) -> bool:
    if gateway_compute_model.ip_address is None:
        logger.warning(
            "Gateway replica %s has no ip_address, cannot update", gateway_compute_model.id
        )
        return False
    if _recently_updated(gateway_compute_model):
        logger.debug(
            "Skipping gateway %s update. Gateway was recently updated.",
            gateway_compute_model.ip_address,
        )
        return False
    connection = await gateway_connections_pool.get_or_add(
        gateway_compute_model.ip_address,
        gateway_compute_model.ssh_private_key,
    )
    logger.debug("Updating gateway %s", connection.ip_address)
    router = _get_gateway_compute_router_config(gateway_compute_model)

    # Build package spec with extras and wheel URL
    gateway_package = get_dstack_gateway_wheel(build, router)
    commands = [
        # prevent update.sh from overwriting itself during execution
        "cp dstack/update.sh dstack/_update.sh",
        f'sh dstack/_update.sh "{gateway_package}" {build}',
        "rm dstack/_update.sh",
    ]
    stdout = await connection.tunnel.aexec("/bin/sh -c '" + " && ".join(commands) + "'")
    if "Update successfully completed" in stdout:
        logger.info("Gateway %s updated", connection.ip_address)
        return True
    return False


def _recently_updated(gateway_compute_model: GatewayComputeModel) -> bool:
    return gateway_compute_model.app_updated_at.replace(
        tzinfo=datetime.timezone.utc
    ) > get_current_datetime() - timedelta(seconds=60)


def _get_gateway_compute_router_config(
    compute: GatewayComputeModel,
) -> Optional[AnyGatewayRouterConfig]:
    if compute.configuration is None:  # pre-0.18.2 gateway
        return None  # gateway routers introduced in 0.19.38
    compute_config: GatewayComputeConfiguration = (
        GatewayComputeConfiguration.__response__.parse_raw(compute.configuration)
    )
    return compute_config.router


async def configure_gateway(
    connection: GatewayConnection,
    attempts: int = GATEWAY_CONFIGURE_ATTEMPTS,
) -> None:
    """
    Try submitting gateway config several times in case gateway's HTTP server is not
    running yet
    """

    logger.debug("Configuring gateway %s", connection.ip_address)

    for attempt in range(attempts - 1):
        try:
            async with connection.client() as client:
                await client.submit_gateway_config()
            break
        except httpx.RequestError as e:
            logger.debug(
                "Failed attempt %s/%s at configuring gateway %s: %r",
                attempt + 1,
                attempts,
                connection.ip_address,
                e,
            )
            await asyncio.sleep(GATEWAY_CONFIGURE_DELAY)
    else:
        async with connection.client() as client:
            await client.submit_gateway_config()

    logger.info("Gateway %s configured", connection.ip_address)


def get_gateway_compute_models(gateway_model: GatewayModel) -> List[GatewayComputeModel]:
    computes = list(gateway_model.gateway_computes)
    if gateway_model.gateway_compute is not None:  # pre-0.20.25 gateway
        computes.append(gateway_model.gateway_compute)
    return computes


def get_gateway_configuration(gateway_model: GatewayModel) -> GatewayConfiguration:
    if gateway_model.configuration is not None:
        return GatewayConfiguration.__response__.parse_raw(gateway_model.configuration)
    # Handle gateways created before GatewayConfiguration was introduced
    return GatewayConfiguration(
        name=gateway_model.name,
        default=False,
        backend=gateway_model.backend.type,
        region=gateway_model.region,
        domain=gateway_model.wildcard_domain,
    )


def get_gateway_compute_configuration(
    gateway_compute: GatewayComputeModel,
    gateway_model: GatewayModel,
) -> GatewayComputeConfiguration:
    if gateway_compute.configuration is not None:
        return GatewayComputeConfiguration.__response__.parse_raw(gateway_compute.configuration)
    # Handle gateways created before GatewayComputeConfiguration was introduced
    gateway_configuration = get_gateway_configuration(gateway_model)
    return GatewayComputeConfiguration(
        project_name=gateway_model.project.name,
        instance_name=f"{gateway_model.name}-{gateway_compute.replica_num}",
        backend=gateway_configuration.backend,
        region=gateway_configuration.region,
        public_ip=True,
        ssh_key_pub=gateway_compute.ssh_public_key,
        certificate=LetsEncryptGatewayCertificate(),
    )


def gateway_model_to_gateway(
    gateway_model: GatewayModel, default_gateway_id: Optional[uuid.UUID]
) -> Gateway:
    """
    Args:
        gateway_model: Gateway model to convert
        default_gateway_id: ID of the default gateway in the project where `gateway_model` is being
            viewed. Can be different from `gateway_model.project` if the gateway is imported.
    """
    is_default = default_gateway_id == gateway_model.id
    configuration = get_gateway_configuration(gateway_model)
    configuration.default = is_default

    all_compute_models = sorted(
        get_gateway_compute_models(gateway_model), key=lambda c: c.replica_num
    )
    relevant_compute_models = []
    for replica_num, compute_models_for_num in itertools.groupby(
        all_compute_models, key=lambda c: c.replica_num
    ):
        relevant_compute_models.append(max(compute_models_for_num, key=lambda c: c.created_at))
    gateway_hostname = None
    replicas = []
    for compute in relevant_compute_models:
        replicas.append(
            GatewayReplica(
                hostname=compute.ip_address,
                replica_num=compute.replica_num,
                backend=compute.backend.type if compute.backend else None,
                region=compute.region,
                created_at=compute.created_at,
                status=compute.status,
                status_message=compute.status_message,
            )
        )
        gateway_hostname = compute.hostname

    return Gateway(
        id=gateway_model.id,
        name=gateway_model.name,
        project_name=gateway_model.project.name,
        hostname=gateway_hostname,
        backend=gateway_model.backend.type,
        region=gateway_model.region,
        wildcard_domain=gateway_model.wildcard_domain,
        default=is_default,
        created_at=gateway_model.created_at,
        status=gateway_model.status,
        status_message=gateway_model.status_message,
        configuration=configuration,
        replicas=replicas,
    )


async def get_plan(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    spec: GatewaySpec,
) -> GatewayPlan:
    effective_spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        spec=spec,
    )
    _validate_gateway_configuration(effective_spec.configuration)

    action = ApplyAction.CREATE
    current_gateway: Optional[Gateway] = None

    if effective_spec.configuration.name is not None:
        current_gateway_model = await get_project_gateway_model_by_reference(
            session=session,
            project=project,
            ref=EntityReference(name=effective_spec.configuration.name, project=None),
            load_gateway_compute=True,
            load_backend_type=True,
        )
        if current_gateway_model is not None:
            if current_gateway_model.to_be_deleted:
                raise ServerClientError(
                    f"Gateway {effective_spec.configuration.name!r} is being deleted. Try again later."
                )
            if current_gateway_model.status == GatewayStatus.FAILED:
                raise ServerClientError(
                    f"Gateway {effective_spec.configuration.name!r} is in FAILED status and"
                    " cannot be updated in-place. Delete it and re-apply."
                )
            current_gateway = gateway_model_to_gateway(
                current_gateway_model, default_gateway_id=project.default_gateway_id
            )
            if _can_update_gateway_in_place(
                diff_models(current_gateway.configuration, effective_spec.configuration)
            ):
                action = ApplyAction.UPDATE

    return GatewayPlan(
        project_name=project.name,
        user=user.name,
        spec=spec,
        effective_spec=effective_spec,
        current_resource=current_gateway,
        action=action,
    )


async def apply_plan(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    plan: ApplyGatewayPlanInput,
    force: bool,
    pipeline_hinter: PipelineHinterProtocol,
) -> Gateway:
    spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        spec=plan.spec,
    )
    new_configuration = spec.configuration
    _validate_gateway_configuration(new_configuration)

    if new_configuration.name is None:
        return await create_gateway(
            session=session,
            user=user,
            project=project,
            configuration=plan.spec.configuration,
            pipeline_hinter=pipeline_hinter,
            effective_configuration=new_configuration,
        )

    async with get_project_gateway_model_by_name_for_update(
        session, project, new_configuration.name
    ) as gateway_model:
        if gateway_model is None:
            return await create_gateway(
                session=session,
                user=user,
                project=project,
                configuration=plan.spec.configuration,
                pipeline_hinter=pipeline_hinter,
                effective_configuration=new_configuration,
            )
        if gateway_model.to_be_deleted:
            raise ServerClientError(
                f"Gateway {new_configuration.name!r} is being deleted. Try again later."
            )
        if gateway_model.status == GatewayStatus.FAILED:
            raise ServerClientError(
                f"Gateway {new_configuration.name!r} is in FAILED status and cannot be updated"
                " in-place. Delete it and re-apply."
            )
        current_configuration = gateway_model_to_gateway(
            gateway_model,
            default_gateway_id=project.default_gateway_id,
        ).configuration

        if not force:
            if (
                plan.current_resource is None
                or plan.current_resource.id != gateway_model.id
                or plan.current_resource.configuration != current_configuration
            ):
                raise ServerClientError(
                    "Failed to apply plan. Resource has been changed. Try again or use force apply."
                )

        diff = diff_models(current_configuration, new_configuration)
        if not _can_update_gateway_in_place(diff):
            raise ServerClientError(
                f"Gateway {new_configuration.name!r} cannot be updated in-place."
                " Delete it and re-apply."
            )

        gateway_model.wildcard_domain = new_configuration.domain
        if new_configuration.replicas != current_configuration.replicas:
            gateway_model.desired_replica_count = (
                new_configuration.replicas
                if new_configuration.replicas is not None
                else GATEWAY_REPLICAS_DEFAULT
            )
        gateway_model.configuration = new_configuration.json()
        gateway_model.last_update_at = get_current_datetime()
        events.emit(
            session,
            f"Gateway updated. Changed fields: {format_diff_fields_for_event(diff)}",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(gateway_model)],
        )
        await session.commit()

    return gateway_model_to_gateway(gateway_model, default_gateway_id=project.default_gateway_id)


def _can_update_gateway_in_place(conf_diff: ModelDiff) -> bool:
    return all(field in _CONF_UPDATABLE_FIELDS for field in conf_diff)


def _validate_gateway_configuration(configuration: GatewayConfiguration):
    check_backend_type_available(configuration.backend)
    if configuration.backend not in BACKENDS_WITH_GATEWAY_SUPPORT:
        raise ServerClientError(
            f"Gateways are not supported for {configuration.backend.value} backend."
            " Available backends with gateway support:"
            f" {[b.value for b in BACKENDS_WITH_GATEWAY_SUPPORT]}."
        )

    if configuration.name is not None:
        validate_dstack_resource_name(configuration.name)

    if configuration.domain is not None:
        # validate that domain can be interpolated
        interpolate_gateway_domain(
            domain=configuration.domain,
            run_project_name="example",
            exception_type=ServerClientError,
        )

    if (
        not configuration.public_ip
        and configuration.backend not in BACKENDS_WITH_PRIVATE_GATEWAY_SUPPORT
    ):
        raise ServerClientError(
            f"Private gateways are not supported for {configuration.backend.value} backend. "
            " Available backends with private gateway support:"
            f" {[b.value for b in BACKENDS_WITH_PRIVATE_GATEWAY_SUPPORT]}."
        )

    replicas = (
        configuration.replicas if configuration.replicas is not None else GATEWAY_REPLICAS_DEFAULT
    )

    if replicas > GATEWAY_MAX_REPLICAS:
        raise ServerClientError(
            f"Cannot provision {replicas} gateway replicas. This server allows at most {GATEWAY_MAX_REPLICAS}"
        )

    if configuration.certificate is not None:
        if configuration.certificate.type == "lets-encrypt" and not configuration.public_ip:
            raise ServerClientError(
                "lets-encrypt certificate type is not supported for private gateways"
            )
        if configuration.certificate.type == "acm" and configuration.backend != BackendType.AWS:
            raise ServerClientError("acm certificate type is supported for aws backend only")
        if replicas > 1:
            raise ServerClientError(
                "Replicated gateways do not support certificates."
                " Set either `certificate: null` or `replicas: 1` in the gateway configuration"
            )

    if configuration.router is not None and replicas > 1:
        raise ServerClientError(
            "The deprecated `router` property is not supported for multi-replica gateways"
        )
