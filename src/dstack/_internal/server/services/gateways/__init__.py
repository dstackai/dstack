import asyncio
import datetime
import uuid
from datetime import timedelta
from functools import partial
from typing import List, Optional, Sequence

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import dstack._internal.utils.random_names as random_names
from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithGatewaySupport,
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
from dstack._internal.core.models.gateways import (
    Gateway,
    GatewayComputeConfiguration,
    GatewayConfiguration,
    GatewaySpec,
    GatewayStatus,
    LetsEncryptGatewayCertificate,
)
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.server import settings
from dstack._internal.server.db import get_db
from dstack._internal.server.models import (
    GatewayComputeModel,
    GatewayModel,
    ProjectModel,
    UserModel,
)
from dstack._internal.server.services.backends import (
    check_backend_type_available,
    get_project_backend_by_type_or_error,
    get_project_backend_with_model_by_type_or_error,
)
from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.services.gateways.pool import gateway_connections_pool
from dstack._internal.server.services.locking import (
    advisory_lock_ctx,
    get_locker,
    string_to_lock_id,
)
from dstack._internal.server.services.plugins import apply_plugin_policies
from dstack._internal.server.utils.common import gather_map_async
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


GATEWAY_CONNECT_ATTEMPTS = 30
GATEWAY_CONNECT_DELAY = 10
GATEWAY_CONFIGURE_ATTEMPTS = 50
GATEWAY_CONFIGURE_DELAY = 3


async def list_project_gateways(session: AsyncSession, project: ProjectModel) -> List[Gateway]:
    gateways = await list_project_gateway_models(session=session, project=project)
    return [gateway_model_to_gateway(g) for g in gateways]


async def get_gateway_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[Gateway]:
    gateway = await get_project_gateway_model_by_name(session=session, project=project, name=name)
    if gateway is None:
        return None
    return gateway_model_to_gateway(gateway)


async def create_gateway_compute(
    project_name: str,
    backend_compute: Compute,
    configuration: GatewayConfiguration,
    backend_id: Optional[uuid.UUID] = None,
) -> GatewayComputeModel:
    assert isinstance(backend_compute, ComputeWithGatewaySupport)
    assert configuration.name is not None

    private_bytes, public_bytes = generate_rsa_key_pair_bytes()
    gateway_ssh_private_key = private_bytes.decode()
    gateway_ssh_public_key = public_bytes.decode()

    compute_configuration = GatewayComputeConfiguration(
        project_name=project_name,
        instance_name=configuration.name,
        backend=configuration.backend,
        region=configuration.region,
        public_ip=configuration.public_ip,
        ssh_key_pub=gateway_ssh_public_key,
        certificate=configuration.certificate,
        tags=configuration.tags,
    )

    gpd = await run_async(
        backend_compute.create_gateway,
        compute_configuration,
    )

    return GatewayComputeModel(
        backend_id=backend_id,
        region=gpd.region,
        ip_address=gpd.ip_address,
        instance_id=gpd.instance_id,
        hostname=gpd.hostname,
        configuration=compute_configuration.json(),
        backend_data=gpd.backend_data,
        ssh_private_key=gateway_ssh_private_key,
        ssh_public_key=gateway_ssh_public_key,
    )


async def create_gateway(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    configuration: GatewayConfiguration,
) -> Gateway:
    spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        # Create pseudo spec until the gateway API is updated to accept spec
        spec=GatewaySpec(configuration=configuration),
    )
    configuration = spec.configuration
    _validate_gateway_configuration(configuration)

    backend_model, _ = await get_project_backend_with_model_by_type_or_error(
        project=project, backend_type=configuration.backend
    )

    lock_namespace = f"gateway_names_{project.name}"
    if get_db().dialect_name == "sqlite":
        # Start new transaction to see committed changes after lock
        await session.commit()
    elif get_db().dialect_name == "postgresql":
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )

    lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)
    async with lock:
        if configuration.name is None:
            configuration.name = await generate_gateway_name(session=session, project=project)

        gateway = GatewayModel(
            name=configuration.name,
            region=configuration.region,
            project_id=project.id,
            backend_id=backend_model.id,
            wildcard_domain=configuration.domain,
            configuration=configuration.json(),
            status=GatewayStatus.SUBMITTED,
            last_processed_at=get_current_datetime(),
        )
        session.add(gateway)
        await session.commit()

        default_gateway = await get_project_default_gateway_model(session=session, project=project)
        if default_gateway is None or configuration.default:
            await set_default_gateway(session=session, project=project, name=configuration.name)
        return gateway_model_to_gateway(gateway)


# NOTE: dstack Sky imports and uses this function
async def connect_to_gateway_with_retry(
    gateway_compute: GatewayComputeModel,
) -> Optional[GatewayConnection]:
    """
    Create gateway connection and add it to connection pool.
    Give gateway sufficient time to become available. In the case of gateway
    being accessed via domain (e.g. Kubernetes LB), it may take some time before
    the domain can be resolved.
    """

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
        # Refetch after lock
        res = await session.execute(
            select(GatewayModel)
            .where(
                GatewayModel.project_id == project.id,
                GatewayModel.name.in_(gateways_names),
            )
            .options(selectinload(GatewayModel.gateway_compute))
            .execution_options(populate_existing=True)
            .order_by(GatewayModel.id)  # take locks in order
            .with_for_update(key_share=True)
        )
        gateway_models = res.scalars().all()
        for gateway_model in gateway_models:
            backend = await get_project_backend_by_type_or_error(
                project=project, backend_type=gateway_model.backend.type
            )
            compute = backend.compute()
            assert isinstance(compute, ComputeWithGatewaySupport)
            gateway_compute_configuration = get_gateway_compute_configuration(gateway_model)
            if (
                gateway_model.gateway_compute is not None
                and gateway_compute_configuration is not None
            ):
                logger.info("Deleting gateway compute for %s...", gateway_model.name)
                try:
                    await run_async(
                        compute.terminate_gateway,
                        gateway_model.gateway_compute.instance_id,
                        gateway_compute_configuration,
                        gateway_model.gateway_compute.backend_data,
                    )
                except Exception:
                    logger.exception(
                        "Error when deleting gateway compute for %s",
                        gateway_model.name,
                    )
                    continue
                logger.info("Deleted gateway compute for %s", gateway_model.name)
            if gateway_model.gateway_compute is not None:
                await gateway_connections_pool.remove(gateway_model.gateway_compute.ip_address)
                gateway_model.gateway_compute.active = False
                gateway_model.gateway_compute.deleted = True
                session.add(gateway_model.gateway_compute)
            await session.delete(gateway_model)
        await session.commit()


async def set_gateway_wildcard_domain(
    session: AsyncSession, project: ProjectModel, name: str, wildcard_domain: Optional[str]
) -> Gateway:
    gateway = await get_project_gateway_model_by_name(
        session=session,
        project=project,
        name=name,
    )
    if gateway is None:
        raise ResourceNotExistsError()
    if gateway.backend.type == BackendType.DSTACK:
        raise ServerClientError("Custom domains for dstack Sky gateway are not supported")
    await session.execute(
        update(GatewayModel)
        .where(
            GatewayModel.project_id == project.id,
            GatewayModel.name == name,
        )
        .values(
            wildcard_domain=wildcard_domain,
        )
    )
    await session.commit()
    gateway = await get_project_gateway_model_by_name(
        session=session,
        project=project,
        name=name,
    )
    if gateway is None:
        raise ResourceNotExistsError()
    return gateway_model_to_gateway(gateway)


async def set_default_gateway(session: AsyncSession, project: ProjectModel, name: str):
    gateway = await get_project_gateway_model_by_name(session=session, project=project, name=name)
    if gateway is None:
        raise ResourceNotExistsError()
    await session.execute(
        update(ProjectModel)
        .where(
            ProjectModel.id == project.id,
        )
        .values(
            default_gateway_id=gateway.id,
        )
    )
    await session.commit()


async def list_project_gateway_models(
    session: AsyncSession, project: ProjectModel
) -> Sequence[GatewayModel]:
    res = await session.execute(select(GatewayModel).where(GatewayModel.project_id == project.id))
    return res.scalars().all()


async def get_project_gateway_model_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[GatewayModel]:
    res = await session.execute(
        select(GatewayModel).where(
            GatewayModel.project_id == project.id, GatewayModel.name == name
        )
    )
    return res.scalar()


async def get_project_default_gateway_model(
    session: AsyncSession, project: ProjectModel
) -> Optional[GatewayModel]:
    res = await session.execute(
        select(GatewayModel).where(GatewayModel.id == project.default_gateway_id)
    )
    return res.scalar_one_or_none()


async def generate_gateway_name(session: AsyncSession, project: ProjectModel) -> str:
    gateways = await list_project_gateway_models(session=session, project=project)
    names = {g.name for g in gateways}
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


async def get_or_add_gateway_connection(
    session: AsyncSession, gateway_id: uuid.UUID
) -> GatewayConnection:
    gateway = await session.get(GatewayModel, gateway_id)
    if gateway is None:
        raise GatewayError("Gateway not found")
    if gateway.gateway_compute is None:
        raise GatewayError("Gateway compute not found")
    try:
        conn = await gateway_connections_pool.get_or_add(
            hostname=gateway.gateway_compute.ip_address,
            id_rsa=gateway.gateway_compute.ssh_private_key,
        )
    except Exception as e:
        logger.warning(
            "Failed to connect to gateway %s: %s", gateway.gateway_compute.ip_address, e
        )
        raise GatewayError("Failed to connect to gateway")
    return conn


async def init_gateways(session: AsyncSession):
    res = await session.execute(
        select(GatewayComputeModel).where(
            # FIXME: should not include computes related to gateways in the `provisioning` status.
            # Causes warnings and delays when restarting the server during gateway provisioning.
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
            gateway_computes,
            lambda g: gateway_connections_pool.get_or_add(g.ip_address, g.ssh_private_key, True),
            return_exceptions=True,
        ):
            if isinstance(error, Exception):
                logger.warning("Failed to connect to gateway %s: %s", gateway.ip_address, error)

        if settings.SKIP_GATEWAY_UPDATE:
            logger.debug("Skipping gateways update due to DSTACK_SKIP_GATEWAY_UPDATE env variable")
        else:
            build = get_dstack_runner_version()

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
    commands = [
        # prevent update.sh from overwriting itself during execution
        "cp dstack/update.sh dstack/_update.sh",
        f"sh dstack/_update.sh {get_dstack_gateway_wheel(build)} {build}",
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


# NOTE: dstack Sky imports and uses this function
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
    gateway_model: GatewayModel,
) -> Optional[GatewayComputeConfiguration]:
    if gateway_model.gateway_compute is None:
        return None
    if gateway_model.gateway_compute.configuration is not None:
        return GatewayComputeConfiguration.__response__.parse_raw(
            gateway_model.gateway_compute.configuration
        )
    # Handle gateways created before GatewayComputeConfiguration was introduced
    return GatewayComputeConfiguration(
        project_name=gateway_model.project.name,
        instance_name=gateway_model.gateway_compute.instance_id,
        backend=gateway_model.backend.type,
        region=gateway_model.gateway_compute.region,
        public_ip=True,
        ssh_key_pub=gateway_model.gateway_compute.ssh_public_key,
        certificate=LetsEncryptGatewayCertificate(),
    )


def gateway_model_to_gateway(gateway_model: GatewayModel) -> Gateway:
    ip_address = ""
    instance_id = ""
    hostname = ""
    if gateway_model.gateway_compute is not None:
        ip_address = gateway_model.gateway_compute.ip_address
        instance_id = gateway_model.gateway_compute.instance_id
        hostname = gateway_model.gateway_compute.hostname
        if hostname is None:
            hostname = ip_address
    backend_type = gateway_model.backend.type
    if gateway_model.backend.type == BackendType.DSTACK:
        backend_type = BackendType.AWS
    configuration = get_gateway_configuration(gateway_model)
    configuration.default = gateway_model.project.default_gateway_id == gateway_model.id
    return Gateway(
        name=gateway_model.name,
        ip_address=ip_address,
        instance_id=instance_id,
        hostname=hostname,
        backend=backend_type,
        region=gateway_model.region,
        wildcard_domain=gateway_model.wildcard_domain,
        default=gateway_model.project.default_gateway_id == gateway_model.id,
        created_at=gateway_model.created_at,
        status=gateway_model.status,
        status_message=gateway_model.status_message,
        configuration=configuration,
    )


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

    if (
        not configuration.public_ip
        and configuration.backend not in BACKENDS_WITH_PRIVATE_GATEWAY_SUPPORT
    ):
        raise ServerClientError(
            f"Private gateways are not supported for {configuration.backend.value} backend. "
            " Available backends with private gateway support:"
            f" {[b.value for b in BACKENDS_WITH_PRIVATE_GATEWAY_SUPPORT]}."
        )

    if configuration.certificate is not None:
        if configuration.certificate.type == "lets-encrypt" and not configuration.public_ip:
            raise ServerClientError(
                "lets-encrypt certificate type is not supported for private gateways"
            )
        if configuration.certificate.type == "acm" and configuration.backend != BackendType.AWS:
            raise ServerClientError("acm certificate type is supported for aws backend only")
