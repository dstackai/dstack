import asyncio
import uuid
from datetime import timezone
from typing import List, Optional, Sequence
from urllib.parse import urlparse

import httpx
import sqlalchemy.orm as sa_orm
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.jobs as jobs_services
import dstack._internal.utils.random_names as random_names
from dstack._internal.core.backends.base.compute import (
    Compute,
    get_dstack_gateway_wheel,
    get_dstack_runner_version,
)
from dstack._internal.core.errors import (
    GatewayError,
    ResourceNotExistsError,
    ServerClientError,
    SSHError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.core.models.runs import (
    Run,
    RunSpec,
    ServiceModelSpec,
    ServiceSpec,
)
from dstack._internal.server import settings
from dstack._internal.server.models import (
    GatewayComputeModel,
    GatewayModel,
    JobModel,
    ProjectModel,
    RunModel,
)
from dstack._internal.server.services.backends import (
    get_project_backend_by_type_or_error,
    get_project_backends_with_models,
)
from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.services.gateways.options import get_service_options
from dstack._internal.server.services.gateways.pool import gateway_connections_pool
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.utils.common import gather_map_async, run_async
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


GATEWAY_CONNECT_ATTEMPTS = 9
GATEWAY_CONNECT_DELAY = 10
GATEWAY_CONFIGURE_ATTEMPTS = 40
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


async def get_project_default_gateway(
    session: AsyncSession, project: ProjectModel
) -> Optional[Gateway]:
    gateway: Optional[GatewayModel] = project.default_gateway
    if gateway is None:
        return None
    return gateway_model_to_gateway(gateway)


async def create_gateway_compute(
    backend_compute: Compute,
    instance_name: str,
    region: str,
    project_id: str,
    backend_id: Optional[uuid.UUID] = None,
) -> GatewayComputeModel:
    private_bytes, public_bytes = generate_rsa_key_pair_bytes()
    gateway_ssh_private_key = private_bytes.decode()
    gateway_ssh_public_key = public_bytes.decode()

    info = await run_async(
        backend_compute.create_gateway,
        instance_name,
        gateway_ssh_public_key,
        region,
        project_id,
    )

    return GatewayComputeModel(
        backend_id=backend_id,
        ip_address=info.ip_address,
        region=info.region,
        instance_id=info.instance_id,
        ssh_private_key=gateway_ssh_private_key,
        ssh_public_key=gateway_ssh_public_key,
    )


async def create_gateway(
    session: AsyncSession,
    project: ProjectModel,
    name: Optional[str],
    backend_type: BackendType,
    region: str,
) -> Gateway:
    # TODO: Gateay creation may take significant time. Make it asynchronous.
    for backend_model, backend in await get_project_backends_with_models(project):
        if backend_model.type == backend_type:
            break
    else:
        raise ResourceNotExistsError()

    if name is None:
        name = await generate_gateway_name(session=session, project=project)

    gateway = GatewayModel(  # reserve name
        name=name,
        region=region,
        project_id=project.id,
        backend_id=backend_model.id,
    )
    session.add(gateway)
    await session.commit()

    if project.default_gateway is None:
        await set_default_gateway(session=session, project=project, name=name)

    try:
        gateway.gateway_compute = await create_gateway_compute(
            backend_compute=backend.compute(),
            instance_name=gateway.name,
            region=region,
            project_id=project.name,
            backend_id=backend_model.id,
        )
        session.add(gateway)
        await session.commit()
        await session.refresh(gateway)
    except Exception:  # rollback, release reserved name
        await session.execute(
            delete(GatewayModel).where(
                GatewayModel.project_id == project.id,
                GatewayModel.name == name,
            )
        )
        await session.commit()
        raise

    connection = await connect_to_gateway_with_retry(gateway.gateway_compute)

    if connection:
        try:
            await configure_gateway(connection)
        except Exception as e:
            logger.error(
                "Failed to configure gateway %s: %r", gateway.gateway_compute.ip_address, e
            )

    return gateway_model_to_gateway(gateway)


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
            connection = await gateway_connections_pool.add(
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


async def delete_gateways(session: AsyncSession, project: ProjectModel, gateways_names: List[str]):
    tasks = []
    gateways = []
    for gateway in await list_project_gateway_models(session=session, project=project):
        if gateway.backend.type == BackendType.DSTACK:
            continue
        if gateway.name not in gateways_names:
            continue
        backend = await get_project_backend_by_type_or_error(project, gateway.backend.type)
        if gateway.gateway_compute is not None:
            tasks.append(
                run_async(
                    backend.compute().terminate_instance,
                    gateway.gateway_compute.instance_id,
                    gateway.gateway_compute.region,  # use LaunchedGatewayInfo.region
                    None,
                )
            )
        else:
            tasks.append(run_async(lambda: ...))
        gateways.append(gateway)
    # terminate in parallel
    terminate_results = await asyncio.gather(*tasks, return_exceptions=True)
    for gateway, error in zip(gateways, terminate_results):
        if isinstance(error, Exception):
            continue  # ignore error, but keep gateway
        if gateway.gateway_compute is not None:
            await gateway_connections_pool.remove(gateway.gateway_compute.ip_address)
            gateway.gateway_compute.deleted = True
            session.add(gateway.gateway_compute)
        await session.delete(gateway)
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


async def generate_gateway_name(session: AsyncSession, project: ProjectModel) -> str:
    gateways = await list_project_gateway_models(session=session, project=project)
    names = {g.name for g in gateways}
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


async def register_service(session: AsyncSession, run_model: RunModel):
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)

    # TODO(egor-s): allow to configure gateway name
    gateway_name: Optional[str] = None
    if gateway_name is None:
        gateway = run_model.project.default_gateway
        if gateway is None:
            raise ResourceNotExistsError("Default gateway is not set")
    else:
        gateway = await get_project_gateway_model_by_name(
            session=session, project=run_model.project, name=gateway_name
        )
        if gateway is None:
            raise ResourceNotExistsError("Gateway does not exist")
    if gateway.gateway_compute is None:
        raise ServerClientError("Gateway has no instance associated with it")

    wildcard_domain = gateway.wildcard_domain.lstrip("*.") if gateway.wildcard_domain else None
    if wildcard_domain is None:
        raise ServerClientError("Domain is required for gateway")
    # we force port 443 for now
    service_spec = ServiceSpec(url=f"https://{run_model.run_name}.{wildcard_domain}")
    if run_spec.configuration.model is not None:
        service_spec.model = ServiceModelSpec(
            name=run_spec.configuration.model.name,
            base_url=f"https://gateway.{wildcard_domain}",
            type=run_spec.configuration.model.type,
        )
        service_spec.options = get_service_options(run_spec.configuration)

    run_model.gateway = gateway
    run_model.service_spec = service_spec.json()

    conn = await gateway_connections_pool.get(gateway.gateway_compute.ip_address)
    if conn is None:
        raise ServerClientError("Gateway is not connected")

    try:
        logger.debug("%s: registering service as %s", fmt(run_model), service_spec.url)
        async with conn.client() as client:
            await client.register_service(
                project=run_model.project.name,
                run_id=run_model.id,
                domain=urlparse(service_spec.url).hostname,
                auth=run_spec.configuration.auth,
                options=service_spec.options,
                ssh_private_key=run_model.project.ssh_private_key,
            )
        logger.info("%s: service is registered as %s", fmt(run_model), service_spec.url)
    except SSHError:
        raise ServerClientError("Gateway tunnel is not working")
    except httpx.RequestError as e:
        raise GatewayError(f"Gateway is not working: {e}")


async def register_replica(
    session: AsyncSession, gateway_id: uuid.UUID, run: Run, job_model: JobModel
):
    conn = await get_gateway_connection(session, gateway_id)
    job_submission = jobs_services.job_model_to_job_submission(job_model)
    try:
        logger.debug("%s: registering replica for service %s", fmt(job_model), run.id.hex)
        async with conn.client() as client:
            await client.register_replica(
                run=run,
                job_submission=job_submission,
            )
        logger.info("%s: replica is registered for service %s", fmt(job_model), run.id.hex)
    except (httpx.RequestError, SSHError) as e:
        raise GatewayError(str(e))


async def unregister_service(session: AsyncSession, run_model: RunModel):
    conn = await get_gateway_connection(session, run_model.gateway_id)
    project = await session.get(ProjectModel, run_model.project_id)
    try:
        logger.debug("%s: unregistering service", fmt(run_model))
        async with conn.client() as client:
            await client.unregister_service(
                project=project.name,
                run_id=run_model.id,
            )
        logger.debug("%s: service is unregistered", fmt(run_model))
    except GatewayError as e:
        # ignore if service is not registered
        logger.warning("%s: unregistering service: %s", fmt(run_model), e)
    except (httpx.RequestError, SSHError) as e:
        raise GatewayError(str(e))


async def unregister_replica(session: AsyncSession, job_model: JobModel):
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(sa_orm.joinedload(RunModel.project))
    )
    run_model = res.scalar()
    if run_model.gateway_id is None:
        return

    conn = await get_gateway_connection(session, run_model.gateway_id)
    try:
        logger.debug(
            "%s: unregistering replica from service %s", fmt(job_model), job_model.run_id.hex
        )
        async with conn.client() as client:
            await client.unregister_replica(
                project=run_model.project.name,
                run_id=run_model.id,
                job_id=job_model.id,
            )
        logger.info(
            "%s: replica is unregistered from service %s", fmt(job_model), job_model.run_id.hex
        )
    except GatewayError as e:
        # ignore if replica is not registered
        logger.warning("%s: unregistering replica from service: %s", fmt(job_model), e)
    except (httpx.RequestError, SSHError) as e:
        raise GatewayError(str(e))


async def get_gateway_connection(
    session: AsyncSession, gateway_id: uuid.UUID
) -> GatewayConnection:
    gateway = await session.get(GatewayModel, gateway_id)
    if gateway is None:
        raise GatewayError("Gateway doesn't exist")
    if gateway.gateway_compute is None:
        raise GatewayError("Gateway is broken, no compute")
    conn = await gateway_connections_pool.get(gateway.gateway_compute.ip_address)
    if conn is None:
        raise GatewayError("Gateway is not connected")
    return conn


async def init_gateways(session: AsyncSession):
    res = await session.execute(
        select(GatewayComputeModel).where(GatewayComputeModel.deleted == False)
    )
    gateway_computes = res.scalars().all()

    if len(gateway_computes) > 0:
        logger.info(f"Connecting to {len(gateway_computes)} gateways...", {"show_path": False})
    for gateway, error in await gather_map_async(
        gateway_computes,
        lambda g: gateway_connections_pool.add(g.ip_address, g.ssh_private_key),
        return_exceptions=True,
    ):
        if isinstance(error, Exception):
            logger.warning("Failed to connect to gateway %s: %s", gateway.ip_address, error)

    if settings.SKIP_GATEWAY_UPDATE:
        logger.debug("Skipping gateway update due to DSTACK_SKIP_GATEWAY_UPDATE env variable")
    else:
        build = get_dstack_runner_version()

        for conn, error in await gather_map_async(
            await gateway_connections_pool.all(),
            lambda c: _update_gateway(c, build),
            return_exceptions=True,
        ):
            if isinstance(error, Exception):
                logger.warning("Failed to update gateway %s: %s", conn.ip_address, error)

    for conn, error in await gather_map_async(
        await gateway_connections_pool.all(),
        configure_gateway,
        return_exceptions=True,
    ):
        if isinstance(error, Exception):
            logger.warning("Failed to configure gateway %s: %r", conn.ip_address, error)


async def _update_gateway(connection: GatewayConnection, build: str):
    logger.debug("Updating gateway %s", connection.ip_address)
    stdout = await connection.tunnel.exec(
        f"/bin/sh dstack/update.sh {get_dstack_gateway_wheel(build)} {build}"
    )
    if "Update successfully completed" in stdout:
        logger.info("Gateway %s updated", connection.ip_address)


async def configure_gateway(connection: GatewayConnection) -> None:
    """
    Try submitting gateway config several times in case gateway's HTTP server is not
    running yet
    """

    logger.debug("Configuring gateway %s", connection.ip_address)

    for attempt in range(GATEWAY_CONFIGURE_ATTEMPTS - 1):
        try:
            async with connection.client() as client:
                await client.submit_gateway_config()
            break
        except httpx.RequestError as e:
            logger.debug(
                "Failed attempt %s/%s at configuring gateway %s: %r",
                attempt + 1,
                GATEWAY_CONFIGURE_ATTEMPTS,
                connection.ip_address,
                e,
            )
            await asyncio.sleep(GATEWAY_CONFIGURE_DELAY)
    else:
        async with connection.client() as client:
            await client.submit_gateway_config()

    logger.info("Gateway %s configured", connection.ip_address)


def gateway_model_to_gateway(gateway_model: GatewayModel) -> Gateway:
    ip_address = ""
    instance_id = ""
    if gateway_model.gateway_compute is not None:
        ip_address = gateway_model.gateway_compute.ip_address
        instance_id = gateway_model.gateway_compute.instance_id
    backend_type = gateway_model.backend.type
    if gateway_model.backend.type == BackendType.DSTACK:
        backend_type = BackendType.AWS
    return Gateway(
        name=gateway_model.name,
        ip_address=ip_address,
        instance_id=instance_id,
        region=gateway_model.region,
        wildcard_domain=gateway_model.wildcard_domain,
        default=gateway_model.project.default_gateway_id == gateway_model.id,
        created_at=gateway_model.created_at.replace(tzinfo=timezone.utc),
        backend=backend_type,
    )
