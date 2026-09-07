import asyncio
import datetime
import itertools
import shlex
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
    get_dstack_gateway_package_and_target_version,
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
from dstack._internal.core.models.common import (
    ApplyAction,
    EntityReference,
    validate_json_extra_ignore,
)
from dstack._internal.core.models.gateways import (
    GATEWAY_REPLICAS_DEFAULT,
    ApplyGatewayPlanInput,
    Gateway,
    GatewayConfiguration,
    GatewayLoadBalancerConfiguration,
    GatewayPlan,
    GatewayReplica,
    GatewayReplicaConfiguration,
    GatewayReplicaStatus,
    GatewaySpec,
    GatewayStatus,
    LetsEncryptGatewayCertificate,
)
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.core.services.diff import ModelDiff, format_diff_fields_for_event
from dstack._internal.core.services.gateways import diff_gateway_configurations
from dstack._internal.proxy.gateway.const import SERVICE_SCALING_WINDOWS
from dstack._internal.proxy.gateway.schemas.stats import PerWindowStats, Stat
from dstack._internal.server import settings
from dstack._internal.server.db import get_db, is_db_postgres, is_db_sqlite
from dstack._internal.server.models import (
    BackendModel,
    ExportedGatewayModel,
    GatewayModel,
    GatewayReplicaModel,
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
from dstack._internal.utils import crypto
from dstack._internal.utils.common import (
    get_current_datetime,
    get_or_error,
    interpolate_gateway_domain,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
_CONF_UPDATABLE_FIELDS = frozenset({"domain", "default", "replicas"})


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


def emit_gateway_replica_status_change_event(
    session: AsyncSession,
    replica_model: GatewayReplicaModel,
    old_status: GatewayReplicaStatus,
    new_status: GatewayReplicaStatus,
    status_message: Optional[str],
    actor: events.AnyActor = events.SystemActor(),
) -> None:
    if old_status == new_status:
        return
    msg = f"Gateway replica status changed {old_status.upper()} -> {new_status.upper()}"
    if status_message is not None:
        msg += f" ({status_message})"
    events.emit(session, msg, actor=actor, targets=[events.Target.from_model(replica_model)])


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
        load_gateway_replica=True,
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
        load_gateway_replica=True,
        load_backend_type=True,
    )
    if gateway is None:
        return None
    return gateway_model_to_gateway(gateway, default_gateway_id=project.default_gateway_id)


def create_gateway_replica_model(
    gateway_model: GatewayModel,
    replica_num: int,
) -> GatewayReplicaModel:
    configuration = get_gateway_configuration(gateway_model)
    replica_name = f"{gateway_model.name}-{replica_num}"

    private_bytes, public_bytes = crypto.generate_rsa_key_pair_bytes()
    gateway_ssh_private_key = private_bytes.decode()
    gateway_ssh_public_key = public_bytes.decode()

    replica_configuration = GatewayReplicaConfiguration(
        project_name=gateway_model.project.name,
        instance_name=replica_name,
        backend=configuration.backend,
        region=configuration.region,
        instance_type=configuration.instance_type,
        public_ip=configuration.public_ip,
        ssh_key_pub=gateway_ssh_public_key,
        certificate=configuration.certificate,
        tags=configuration.tags,
    )

    now = get_current_datetime()
    return GatewayReplicaModel(
        id=uuid.uuid4(),
        name=replica_name,
        gateway_id=gateway_model.id,
        gateway=gateway_model,
        backend_id=gateway_model.backend_id,
        replica_num=replica_num,
        configuration=replica_configuration.model_dump_json(),
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
            configuration=configuration.model_dump_json(),
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
        if default_gateway is None and configuration.default is None or configuration.default:
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
            load_gateway_replica=True,
            load_backend_type=True,
        )
        assert gateway is not None
        return gateway_model_to_gateway(
            gateway, default_gateway_id=default_gateway.id if default_gateway is not None else None
        )


async def connect_to_gateway_replica_with_retry(
    gateway_replica: GatewayReplicaModel,
) -> Optional[GatewayConnection]:
    """
    Create a gateway replica connection and add it to the connection pool.
    Give the gateway replica sufficient time to become available. In the case of the replica
    being accessed via domain (e.g. Kubernetes LB), it may take some time before
    the domain can be resolved.
    """

    if gateway_replica.ip_address is None:
        logger.warning("Gateway replica %s has no ip_address, cannot connect", gateway_replica.id)
        return None

    connection = None

    for attempt in range(GATEWAY_CONNECT_ATTEMPTS):
        try:
            connection = await gateway_connections_pool.get_or_add(
                gateway_replica.ip_address, gateway_replica.ssh_private_key
            )
            break
        except SSHError as e:
            if attempt < GATEWAY_CONNECT_ATTEMPTS - 1:
                logger.debug(
                    "Failed to connect to gateway replica %s: %s", gateway_replica.ip_address, e
                )
                await asyncio.sleep(GATEWAY_CONNECT_DELAY)
            else:
                logger.error(
                    "Failed to connect to gateway replica %s: %s", gateway_replica.ip_address, e
                )

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
                gateway.configuration = conf.model_dump_json()
            events.emit(
                session,
                f"Gateway wildcard domain changed {old_domain!r} -> {gateway.wildcard_domain!r}",
                actor=events.UserActor.from_user(user),
                targets=[events.Target.from_model(gateway)],
            )
            await session.commit()
    return gateway_model_to_gateway(gateway, default_gateway_id=project.default_gateway_id)


async def set_default_gateway(
    session: AsyncSession,
    project: ProjectModel,
    ref: EntityReference,
    user: Optional[UserModel],
    commit: bool = True,
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
    if commit:
        await session.commit()


async def unset_default_gateway(
    session: AsyncSession, project: ProjectModel, expect_gateway_id: uuid.UUID, user: UserModel
) -> None:
    gateway = await get_project_default_gateway_model(session, project)
    if gateway is None or gateway.id != expect_gateway_id:
        return
    await session.execute(
        update(ProjectModel).where(ProjectModel.id == project.id).values(default_gateway_id=None)
    )
    events.emit(
        session,
        "Gateway unset as project default",
        actor=events.UserActor.from_user(user),
        targets=[
            events.Target.from_model(gateway),
            events.Target.from_model(project),
        ],
    )


async def list_project_gateway_models(
    session: AsyncSession,
    project: ProjectModel,
    include_imported: bool = False,
    load_gateway_replica: bool = False,
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
    if load_gateway_replica:
        stmt = stmt.options(
            joinedload(GatewayModel.gateway_replica)
            .joinedload(GatewayReplicaModel.backend)
            .load_only(BackendModel.type)
        )
        stmt = stmt.options(
            selectinload(GatewayModel.gateway_replicas)
            .joinedload(GatewayReplicaModel.backend)
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
    load_gateway_replica: bool = False,
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
    if load_gateway_replica:
        stmt = stmt.options(
            joinedload(GatewayModel.gateway_replica)
            .joinedload(GatewayReplicaModel.backend)
            .load_only(BackendModel.type)
        )
        stmt = stmt.options(
            selectinload(GatewayModel.gateway_replicas)
            .joinedload(GatewayReplicaModel.backend)
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
                    joinedload(GatewayModel.gateway_replica)
                    .joinedload(GatewayReplicaModel.backend)
                    .load_only(BackendModel.type)
                )
                .options(
                    selectinload(GatewayModel.gateway_replicas)
                    .joinedload(GatewayReplicaModel.backend)
                    .load_only(BackendModel.type)
                )
                .options(joinedload(GatewayModel.backend).load_only(BackendModel.type))
                .with_for_update(key_share=True, of=GatewayModel)
            )
            yield res.scalar_one_or_none()


async def get_project_default_gateway_model(
    session: AsyncSession,
    project: ProjectModel,
    load_gateway_replica: bool = False,
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
    if load_gateway_replica:
        stmt = stmt.options(
            joinedload(GatewayModel.gateway_replica)
            .joinedload(GatewayReplicaModel.backend)
            .load_only(BackendModel.type)
        )
        stmt = stmt.options(
            selectinload(GatewayModel.gateway_replicas)
            .joinedload(GatewayReplicaModel.backend)
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
    gateway_replicas: Sequence[GatewayReplicaModel],
) -> List[GatewayConnection]:
    running_replicas = [r for r in gateway_replicas if r.status == GatewayReplicaStatus.RUNNING]
    if not running_replicas:
        raise GatewayError("Gateway replica not found")
    connections: List[GatewayConnection] = []
    for replica in running_replicas:
        if replica.ip_address is None:
            logger.warning("Gateway replica %s has no ip_address", replica.id)
            raise GatewayError("Failed to connect to gateway replica")
        try:
            conn = await gateway_connections_pool.get_or_add(
                hostname=replica.ip_address,
                id_rsa=replica.ssh_private_key,
            )
            connections.append(conn)
        except Exception as e:
            logger.warning("Failed to connect to gateway replica %s: %s", replica.ip_address, e)
            raise GatewayError("Failed to connect to gateway replica")
    return connections


async def get_combined_gateway_stats(
    gateway_replicas: Sequence[GatewayReplicaModel],
    project_name: str,
    run_name: str,
) -> Optional[PerWindowStats]:
    """
    Return stats for *run_name* aggregated across all gateway replicas.
    """
    try:
        # FIXME: once a gateway replica is scaled in, its connection is no longer available and its
        # stats are lost, potentially resulting in incorrect service scaling decisions.
        connections = await get_or_add_gateway_connections(gateway_replicas)
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
        select(GatewayReplicaModel).where(
            GatewayReplicaModel.status == GatewayReplicaStatus.RUNNING,
            GatewayReplicaModel.active == True,
            GatewayReplicaModel.deleted == False,
        )
    )
    gateway_replicas = res.scalars().all()

    if len(gateway_replicas) > 0:
        logger.info(
            f"Connecting to {len(gateway_replicas)} gateway replicas...", {"show_path": False}
        )

    async with advisory_lock_ctx(
        bind=session,
        dialect_name=get_db().dialect_name,
        resource="gateway_tunnels",
    ):
        for gateway_replica, error in await gather_map_async(
            [r for r in gateway_replicas if r.ip_address],
            lambda r: gateway_connections_pool.get_or_add(
                get_or_error(r.ip_address), r.ssh_private_key, True
            ),
            return_exceptions=True,
        ):
            if isinstance(error, Exception):
                logger.warning(
                    "Failed to connect to gateway replica %s: %s",
                    gateway_replica.ip_address,
                    error,
                )

        if settings.SKIP_GATEWAY_UPDATE:
            logger.debug(
                "Skipping gateway replicas update due to DSTACK_SKIP_GATEWAY_UPDATE env variable"
            )
        else:
            gateway_package, target_version = get_dstack_gateway_package_and_target_version()

            for gateway_replica, res in await gather_map_async(
                gateway_replicas,
                lambda r: _update_gateway_replica(r, gateway_package, target_version),
                return_exceptions=True,
            ):
                if isinstance(res, Exception):
                    logger.warning(
                        "Failed to update gateway replica %s: %s", gateway_replica.ip_address, res
                    )
                elif isinstance(res, bool) and res:
                    gateway_replica.app_updated_at = get_current_datetime()

        for connection, error in await gather_map_async(
            await gateway_connections_pool.all(),
            # Need several attempts to handle short gateway replica downtime after update
            partial(configure_gateway_replica, attempts=7),
            return_exceptions=True,
        ):
            if isinstance(error, Exception):
                logger.warning(
                    "Failed to configure gateway replica %s: %r", connection.ip_address, error
                )


async def _update_gateway_replica(
    gateway_replica_model: GatewayReplicaModel,
    gateway_package: str,
    target_version: str | None,
) -> bool:
    if gateway_replica_model.ip_address is None:
        logger.warning(
            "Gateway replica %s has no ip_address, cannot update", gateway_replica_model.id
        )
        return False
    if _recently_updated(gateway_replica_model):
        logger.debug(
            "Skipping gateway replica %s update. Gateway replica was recently updated.",
            gateway_replica_model.ip_address,
        )
        return False
    connection = await gateway_connections_pool.get_or_add(
        gateway_replica_model.ip_address,
        gateway_replica_model.ssh_private_key,
    )
    logger.debug("Updating gateway replica %s", connection.ip_address)

    command = (
        "/bin/sh -c "
        + shlex.quote(_GATEWAY_UPDATE_SCRIPT)
        + " sh "  # $0 placeholder
        + shlex.quote(gateway_package)
        + " "
        + shlex.quote(target_version or "")
    )
    stdout = await connection.tunnel.aexec(command)
    if "Update successfully completed" in stdout:
        logger.info("Gateway replica %s updated", connection.ip_address)
        return True
    return False


# Blue/green: install the new build into the currently inactive venv and flip to it
_GATEWAY_UPDATE_SCRIPT = """\
set -e
gateway_package="$1"
build="$2"
root=/home/ubuntu/dstack
if [ -f "$root/version" ]; then
  version=$(cat "$root/version")
else
  version=blue
fi
if [ -n "$build" ]; then
  current_build=$("$root/$version/bin/pip" show dstack | grep Version | awk '{print $2}')
  if [ "$current_build" = "$build" ]; then
    echo "The build $build is already installed. Skipping..."
    exit 0
  fi
fi
if [ "$version" = blue ]; then
  version=green
else
  version=blue
fi
# dstack-gateway is a pre-0.21.4 package that may still be installed and require a conflicting dstack version
"$root/$version/bin/pip" uninstall -y dstack-gateway dstack
"$root/$version/bin/pip" cache remove dstack
"$root/$version/bin/pip" install "$gateway_package"
sudo "$root/$version/bin/python" -m dstack._internal.proxy.gateway.systemd install
echo "$version" > "$root/version"
sudo systemctl daemon-reload
sudo systemctl restart dstack.gateway
echo "Update successfully completed"
"""


def _recently_updated(gateway_replica_model: GatewayReplicaModel) -> bool:
    return gateway_replica_model.app_updated_at.replace(
        tzinfo=datetime.timezone.utc
    ) > get_current_datetime() - timedelta(seconds=60)


async def configure_gateway_replica(
    connection: GatewayConnection,
    attempts: int = GATEWAY_CONFIGURE_ATTEMPTS,
) -> None:
    """
    Try submitting gateway config to the replica several times in case its HTTP server is not
    running yet
    """

    logger.debug("Configuring gateway replica %s", connection.ip_address)

    for attempt in range(attempts - 1):
        try:
            async with connection.client() as client:
                await client.submit_gateway_config()
            break
        except httpx.RequestError as e:
            logger.debug(
                "Failed attempt %s/%s at configuring gateway replica %s: %r",
                attempt + 1,
                attempts,
                connection.ip_address,
                e,
            )
            await asyncio.sleep(GATEWAY_CONFIGURE_DELAY)
    else:
        async with connection.client() as client:
            await client.submit_gateway_config()

    logger.info("Gateway replica %s configured", connection.ip_address)


def get_gateway_replica_models(gateway_model: GatewayModel) -> List[GatewayReplicaModel]:
    replicas = list(gateway_model.gateway_replicas)
    if gateway_model.gateway_replica is not None:  # pre-0.20.25 gateway
        replicas.append(gateway_model.gateway_replica)
    return replicas


async def skip_gateway_replicas_min_processing_interval(
    session: AsyncSession, gateway_id: uuid.UUID
) -> None:
    await session.execute(
        update(GatewayReplicaModel)
        .where(
            or_(
                GatewayReplicaModel.gateway_id == gateway_id,
                GatewayReplicaModel.id.in_(
                    select(GatewayModel.gateway_replica_id).where(GatewayModel.id == gateway_id)
                ),
            )
        )
        .values(skip_min_processing_interval=True)
    )


def get_gateway_configuration(gateway_model: GatewayModel) -> GatewayConfiguration:
    if gateway_model.configuration is not None:
        return validate_json_extra_ignore(GatewayConfiguration, gateway_model.configuration)
    # Handle gateways created before GatewayConfiguration was introduced
    return GatewayConfiguration(
        name=gateway_model.name,
        backend=gateway_model.backend.type,
        region=gateway_model.region,
        domain=gateway_model.wildcard_domain,
    )


def get_gateway_replica_configuration(
    gateway_replica: GatewayReplicaModel,
    gateway_model: GatewayModel,
) -> GatewayReplicaConfiguration:
    if gateway_replica.configuration is not None:
        return validate_json_extra_ignore(
            GatewayReplicaConfiguration, gateway_replica.configuration
        )
    # Handle gateways created before GatewayReplicaConfiguration was introduced
    gateway_configuration = get_gateway_configuration(gateway_model)
    return GatewayReplicaConfiguration(
        project_name=gateway_model.project.name,
        instance_name=f"{gateway_model.name}-{gateway_replica.replica_num}",
        backend=gateway_configuration.backend,
        region=gateway_configuration.region,
        public_ip=True,
        ssh_key_pub=gateway_replica.ssh_public_key,
        certificate=LetsEncryptGatewayCertificate(),
    )


def get_gateway_lb_configuration(
    gateway_model: GatewayModel,
) -> GatewayLoadBalancerConfiguration:
    configuration = get_gateway_configuration(gateway_model)
    return GatewayLoadBalancerConfiguration(
        project_name=gateway_model.project.name,
        gateway_name=gateway_model.name,
        region=configuration.region,
        public_ip=configuration.public_ip,
        certificate=configuration.certificate,
        tags=configuration.tags,
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

    all_replica_models = sorted(
        get_gateway_replica_models(gateway_model), key=lambda r: r.replica_num
    )
    relevant_replica_models: list[GatewayReplicaModel] = []
    for replica_num, replica_models_for_num in itertools.groupby(
        all_replica_models, key=lambda r: r.replica_num
    ):
        relevant_replica_models.append(max(replica_models_for_num, key=lambda r: r.created_at))
    replicas = []
    for replica_model in relevant_replica_models:
        replicas.append(
            GatewayReplica(
                hostname=replica_model.ip_address,
                replica_num=replica_model.replica_num,
                backend=replica_model.backend.type,
                region=replica_model.region,
                created_at=replica_model.created_at,
                status=replica_model.status,
                status_message=replica_model.status_message,
            )
        )

    return Gateway(
        id=gateway_model.id,
        name=gateway_model.name,
        project_name=gateway_model.project.name,
        hostname=gateway_model.hostname,
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
            load_gateway_replica=True,
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
                diff_gateway_configurations(
                    current_gateway.configuration,
                    effective_spec.configuration,
                )
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

        diff = diff_gateway_configurations(
            current_configuration,
            new_configuration,
        )
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
        if new_configuration.default is True:
            await set_default_gateway(
                session=session,
                project=project,
                ref=EntityReference(name=gateway_model.name, project=None),
                user=user,
                commit=False,
            )
        elif new_configuration.default is False:
            await unset_default_gateway(
                session=session,
                project=project,
                expect_gateway_id=gateway_model.id,
                user=user,
            )
        gateway_model.configuration = new_configuration.model_dump_json()
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

    if configuration.load_balancer is not None:
        if configuration.load_balancer.type == "alb":
            if configuration.backend != BackendType.AWS:
                raise ServerClientError(
                    "`load_balancer: { type: alb }` is supported for `aws` backend only"
                )
            if configuration.certificate is not None and configuration.certificate.type != "acm":
                raise ServerClientError(
                    "`load_balancer: { type: alb }` can only be used with `certificate: null` or"
                    " `certificate: { type: acm }`"
                )

    if configuration.certificate is not None:
        if configuration.certificate.type == "lets-encrypt" and not configuration.public_ip:
            raise ServerClientError(
                "lets-encrypt certificate type is not supported for private gateways"
            )
        if configuration.certificate.type == "acm" and configuration.backend != BackendType.AWS:
            raise ServerClientError("acm certificate type is supported for aws backend only")
        if configuration.certificate.type == "lets-encrypt" and replicas > 1:
            err = (
                "The `lets-encrypt` certificate type is not supported for gateways with `replicas`"
                " greater than `1`. To create a replicated gateway, set the `certificate`"
                " configuration property to one of the supported values, such as"
                " `certificate: null` (no HTTPS)"
            )
            if configuration.backend == BackendType.AWS:
                err += " or `certificate: { type: acm, arn: <arn> }` (AWS ACM)"
            raise ServerClientError(err)
