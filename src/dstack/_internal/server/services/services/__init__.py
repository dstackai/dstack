"""
Application logic related to `type: service` runs.
"""

import uuid
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

import dstack._internal.server.services.jobs as jobs_services
from dstack._internal.core.errors import (
    GatewayError,
    ResourceNotExistsError,
    ServerClientError,
    SSHError,
)
from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.core.models.configurations import SERVICE_HTTPS_DEFAULT, ServiceConfiguration
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewayStatus
from dstack._internal.core.models.runs import Run, RunSpec, ServiceModelSpec, ServiceSpec
from dstack._internal.server import settings
from dstack._internal.server.models import GatewayModel, JobModel, ProjectModel, RunModel
from dstack._internal.server.services.gateways import (
    get_gateway_configuration,
    get_or_add_gateway_connection,
    get_project_gateway_model_by_name,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.services.options import get_service_options
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def register_service(session: AsyncSession, run_model: RunModel, run_spec: RunSpec):
    assert is_core_model_instance(run_spec.configuration, ServiceConfiguration)

    if isinstance(run_spec.configuration.gateway, str):
        gateway = await get_project_gateway_model_by_name(
            session=session, project=run_model.project, name=run_spec.configuration.gateway
        )
        if gateway is None:
            raise ResourceNotExistsError(
                f"Gateway {run_spec.configuration.gateway} does not exist"
            )
    elif run_spec.configuration.gateway == False:
        gateway = None
    else:
        gateway = run_model.project.default_gateway

    if gateway is not None:
        service_spec = await _register_service_in_gateway(session, run_model, run_spec, gateway)
        run_model.gateway = gateway
    elif not settings.FORBID_SERVICES_WITHOUT_GATEWAY:
        service_spec = _register_service_in_server(run_model, run_spec)
    else:
        raise ResourceNotExistsError(
            "This dstack-server installation forbids services without a gateway."
            " Please configure a gateway."
        )
    run_model.service_spec = service_spec.json()


async def _register_service_in_gateway(
    session: AsyncSession, run_model: RunModel, run_spec: RunSpec, gateway: GatewayModel
) -> ServiceSpec:
    if gateway.gateway_compute is None:
        raise ServerClientError("Gateway has no instance associated with it")

    if gateway.status != GatewayStatus.RUNNING:
        raise ServerClientError("Gateway status is not running")

    gateway_configuration = get_gateway_configuration(gateway)
    service_https = _get_service_https(run_spec, gateway_configuration)
    service_protocol = "https" if service_https else "http"

    if service_https and gateway_configuration.certificate is None:
        raise ServerClientError(
            "Cannot run HTTPS service on gateway with no SSL certificates configured"
        )

    gateway_https = _get_gateway_https(gateway_configuration)
    gateway_protocol = "https" if gateway_https else "http"

    wildcard_domain = gateway.wildcard_domain.lstrip("*.") if gateway.wildcard_domain else None
    if wildcard_domain is None:
        raise ServerClientError("Domain is required for gateway")
    service_spec = get_service_spec(
        configuration=run_spec.configuration,
        service_url=f"{service_protocol}://{run_model.run_name}.{wildcard_domain}",
        model_url=f"{gateway_protocol}://gateway.{wildcard_domain}",
    )

    conn = await get_or_add_gateway_connection(session, gateway.id)
    try:
        logger.debug("%s: registering service as %s", fmt(run_model), service_spec.url)
        async with conn.client() as client:
            await client.register_service(
                project=run_model.project.name,
                run_name=run_model.run_name,
                domain=urlparse(service_spec.url).hostname,
                service_https=service_https,
                gateway_https=gateway_https,
                auth=run_spec.configuration.auth,
                client_max_body_size=settings.DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE,
                options=service_spec.options,
                ssh_private_key=run_model.project.ssh_private_key,
            )
        logger.info("%s: service is registered as %s", fmt(run_model), service_spec.url)
    except SSHError:
        raise ServerClientError("Gateway tunnel is not working")
    except httpx.RequestError as e:
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(f"Gateway is not working: {e!r}")

    return service_spec


def _register_service_in_server(run_model: RunModel, run_spec: RunSpec) -> ServiceSpec:
    if run_spec.configuration.https != SERVICE_HTTPS_DEFAULT:
        # Note: if the user sets `https: <default-value>`, it will be ignored silently
        # TODO: in 0.19, make `https` Optional to be able to tell if it was set or omitted
        raise ServerClientError(
            "The `https` configuration property is not applicable when running services without a gateway. "
            "Please configure a gateway or remove the `https` property from the service configuration"
        )
    if run_spec.configuration.replicas.min != run_spec.configuration.replicas.max:
        raise ServerClientError(
            "Auto-scaling is not yet supported when running services without a gateway. "
            "Please configure a gateway or set `replicas` to a fixed value in the service configuration"
        )
    return get_service_spec(
        configuration=run_spec.configuration,
        service_url=f"/proxy/services/{run_model.project.name}/{run_model.run_name}/",
        model_url=f"/proxy/models/{run_model.project.name}/",
    )


def get_service_spec(
    configuration: ServiceConfiguration, service_url: str, model_url: str
) -> ServiceSpec:
    service_spec = ServiceSpec(url=service_url)
    if configuration.model is not None:
        service_spec.model = ServiceModelSpec(
            name=configuration.model.name,
            base_url=model_url,
            type=configuration.model.type,
        )
        service_spec.options = get_service_options(configuration)
    return service_spec


async def register_replica(
    session: AsyncSession, gateway_id: Optional[uuid.UUID], run: Run, job_model: JobModel
):
    if gateway_id is None:  # in-server proxy
        return
    conn = await get_or_add_gateway_connection(session, gateway_id)
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
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(repr(e))


async def unregister_service(session: AsyncSession, run_model: RunModel):
    if run_model.gateway_id is None:  # in-server proxy
        return
    conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
    res = await session.execute(
        select(ProjectModel).where(ProjectModel.id == run_model.project_id)
    )
    project = res.scalar_one()
    try:
        logger.debug("%s: unregistering service", fmt(run_model))
        async with conn.client() as client:
            await client.unregister_service(
                project=project.name,
                run_name=run_model.run_name,
            )
        logger.debug("%s: service is unregistered", fmt(run_model))
    except GatewayError as e:
        # ignore if service is not registered
        logger.warning("%s: unregistering service: %s", fmt(run_model), e)
    except (httpx.RequestError, SSHError) as e:
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(repr(e))


async def unregister_replica(session: AsyncSession, job_model: JobModel):
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(joinedload(RunModel.project).joinedload(ProjectModel.backends))
    )
    run_model = res.unique().scalar_one()
    if run_model.gateway_id is None:
        # not a service or served by in-server proxy
        return

    conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
    try:
        logger.debug(
            "%s: unregistering replica from service %s", fmt(job_model), job_model.run_id.hex
        )
        async with conn.client() as client:
            await client.unregister_replica(
                project=run_model.project.name,
                run_name=run_model.run_name,
                job_id=job_model.id,
            )
        logger.info(
            "%s: replica is unregistered from service %s", fmt(job_model), job_model.run_id.hex
        )
    except GatewayError as e:
        # ignore if replica is not registered
        logger.warning("%s: unregistering replica from service: %s", fmt(job_model), e)
    except (httpx.RequestError, SSHError) as e:
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(repr(e))


def _get_service_https(run_spec: RunSpec, configuration: GatewayConfiguration) -> bool:
    if not run_spec.configuration.https:
        return False
    if configuration.certificate is not None and configuration.certificate.type == "acm":
        return False
    return True


def _get_gateway_https(configuration: GatewayConfiguration) -> bool:
    if configuration.certificate is not None and configuration.certificate.type == "acm":
        return False
    if configuration.certificate is not None and configuration.certificate.type == "lets-encrypt":
        return True
    return False
