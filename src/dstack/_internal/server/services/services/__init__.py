"""
Application logic related to `type: service` runs.
"""

import json
import uuid
from datetime import datetime
from functools import partial
from typing import Optional

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
from dstack._internal.core.models.configurations import (
    DEFAULT_REPLICA_GROUP_NAME,
    SERVICE_HTTPS_DEFAULT,
    ServiceConfiguration,
)
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewayStatus
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.routers import (
    AnyServiceRouterConfig,
    RouterType,
    SGLangServiceRouterConfig,
)
from dstack._internal.core.models.runs import JobSpec, Run, RunSpec, ServiceModelSpec, ServiceSpec
from dstack._internal.core.models.services import OpenAIChatModel
from dstack._internal.proxy.gateway.const import SERVICE_ALREADY_REGISTERED_ERROR_TEMPLATE
from dstack._internal.server import settings
from dstack._internal.server.models import GatewayModel, JobModel, ProjectModel, RunModel
from dstack._internal.server.services import events
from dstack._internal.server.services.gateways import (
    get_gateway_configuration,
    get_or_add_gateway_connection,
    get_project_default_gateway_model,
    get_project_gateway_model_by_name,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.services.autoscalers import get_service_scaler
from dstack._internal.server.services.services.options import get_service_options
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def _gateway_has_sglang_router(config: GatewayConfiguration) -> bool:
    return config.router is not None and config.router.type == RouterType.SGLANG.value


def _build_service_router_config(
    gateway_configuration: GatewayConfiguration,
    service_configuration: ServiceConfiguration,
) -> Optional[AnyServiceRouterConfig]:
    """
    Build router config from gateway (type, policy) + service (pd_disaggregation, policy override).
    Service's policy overrides gateway's if present. Keeps backward compat: SGLang enabled
    automatically when gateway has it configured.
    """
    if not _gateway_has_sglang_router(gateway_configuration):
        return None

    gateway_router = gateway_configuration.router
    assert gateway_router is not None  # ensured by _gateway_has_sglang_router
    router_type = gateway_router.type
    policy = gateway_router.policy

    service_router = service_configuration.router
    if service_router is not None and isinstance(service_router, SGLangServiceRouterConfig):
        policy = service_router.policy
        pd_disaggregation = service_router.pd_disaggregation
    else:
        pd_disaggregation = False

    return SGLangServiceRouterConfig(
        type=router_type,
        policy=policy,
        pd_disaggregation=pd_disaggregation,
    )


async def register_service(session: AsyncSession, run_model: RunModel, run_spec: RunSpec):
    assert isinstance(run_spec.configuration, ServiceConfiguration)

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
        gateway = await get_project_default_gateway_model(
            session=session, project=run_model.project
        )
        if gateway is None and run_spec.configuration.gateway == True:
            raise ResourceNotExistsError(
                "The service requires a gateway, but there is no default gateway in the project"
            )

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
    assert run_spec.configuration.type == "service"

    if gateway.gateway_compute is None:
        raise ServerClientError("Gateway has no instance associated with it")

    if gateway.status != GatewayStatus.RUNNING:
        raise ServerClientError("Gateway status is not running")

    gateway_configuration = get_gateway_configuration(gateway)

    # Check: service specifies SGLang router but gateway does not have it
    service_router = run_spec.configuration.router
    service_wants_sglang = service_router is not None and isinstance(
        service_router, SGLangServiceRouterConfig
    )
    if service_wants_sglang and not _gateway_has_sglang_router(gateway_configuration):
        raise ServerClientError(
            "Service requires gateway with SGLang router but gateway "
            f"'{gateway.name}' does not have the SGLang router configured."
        )

    service_https = _get_service_https(run_spec, gateway_configuration)
    router = _build_service_router_config(gateway_configuration, run_spec.configuration)
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
    service_url = f"{service_protocol}://{run_model.run_name}.{wildcard_domain}"
    if isinstance(run_spec.configuration.model, OpenAIChatModel):
        model_url = service_url + run_spec.configuration.model.prefix
    else:
        model_url = f"{gateway_protocol}://gateway.{wildcard_domain}"
    service_spec = get_service_spec(
        configuration=run_spec.configuration,
        service_url=service_url,
        model_url=model_url,
    )

    domain = service_spec.get_domain()
    assert domain is not None

    _, conn = await get_or_add_gateway_connection(session, gateway.id)
    try:
        logger.debug("%s: registering service as %s", fmt(run_model), service_spec.url)
        async with conn.client() as client:
            do_register = partial(
                client.register_service,
                project=run_model.project.name,
                run_name=run_model.run_name,
                domain=domain,
                service_https=service_https,
                gateway_https=gateway_https,
                auth=run_spec.configuration.auth,
                client_max_body_size=settings.DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE,
                options=service_spec.options,
                rate_limits=run_spec.configuration.rate_limits,
                ssh_private_key=run_model.project.ssh_private_key,
                router=router,
            )
            try:
                await do_register()
            except GatewayError as e:
                if e.msg == SERVICE_ALREADY_REGISTERED_ERROR_TEMPLATE.format(
                    ref=f"{run_model.project.name}/{run_model.run_name}"
                ):
                    # Happens if there was a communication issue with the gateway when last unregistering
                    logger.warning(
                        "Service %s/%s is dangling on gateway %s, unregistering and re-registering",
                        run_model.project.name,
                        run_model.run_name,
                        gateway.name,
                    )
                    await client.unregister_service(
                        project=run_model.project.name,
                        run_name=run_model.run_name,
                    )
                    await do_register()
                else:
                    raise
    except SSHError:
        raise ServerClientError("Gateway tunnel is not working")
    except httpx.RequestError as e:
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(f"Gateway is not working: {e!r}")

    events.emit(
        session,
        "Service registered in gateway",
        actor=events.SystemActor(),
        targets=[
            events.Target.from_model(run_model),
            events.Target.from_model(gateway),
        ],
    )
    return service_spec


def _register_service_in_server(run_model: RunModel, run_spec: RunSpec) -> ServiceSpec:
    assert run_spec.configuration.type == "service"
    if (
        run_spec.configuration.router is not None
        and run_spec.configuration.router.type == RouterType.SGLANG
    ):
        raise ServerClientError(
            "Service with SGLang router configuration requires a gateway. "
            "Please configure a gateway with the SGLang router enabled."
        )
    if run_spec.configuration.https not in (
        None,
        "auto",
        True,  # Default set by pre-0.20.12 clients. TODO(0.21.0?): forbid True too.
    ):
        raise ServerClientError(
            f"Setting `https: {run_spec.configuration.https}` is not allowed without a gateway."
            " Please configure a gateway or remove the `https` property from the service configuration"
        )
    # Check if any group has autoscaling (min != max)
    has_autoscaling = any(
        group.count.min != group.count.max for group in run_spec.configuration.replica_groups
    )
    if has_autoscaling:
        raise ServerClientError(
            "Auto-scaling is not supported when running services without a gateway."
            " Please configure a gateway or set `replicas` to a fixed value in the service configuration"
        )
    if run_spec.configuration.rate_limits:
        raise ServerClientError(
            "Rate limits are not supported when running services without a gateway."
            " Please configure a gateway or remove `rate_limits` from the service configuration"
        )
    service_url = f"/proxy/services/{run_model.project.name}/{run_model.run_name}/"
    if isinstance(run_spec.configuration.model, OpenAIChatModel):
        model_url = service_url.rstrip("/") + run_spec.configuration.model.prefix
    else:
        model_url = f"/proxy/models/{run_model.project.name}/"
    return get_service_spec(
        configuration=run_spec.configuration,
        service_url=service_url,
        model_url=model_url,
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
    session: AsyncSession,
    gateway_id: Optional[uuid.UUID],
    run: Run,
    job_model: JobModel,
    ssh_head_proxy: Optional[SSHConnectionParams],
    ssh_head_proxy_private_key: Optional[str],
):
    gateway = None
    if gateway_id is not None:
        gateway, conn = await get_or_add_gateway_connection(session, gateway_id)
        job_submission = jobs_services.job_model_to_job_submission(job_model)
        try:
            logger.debug("%s: registering replica for service %s", fmt(job_model), run.id.hex)
            async with conn.client() as client:
                await client.register_replica(
                    run=run,
                    job_spec=JobSpec.__response__.parse_raw(job_model.job_spec_data),
                    job_submission=job_submission,
                    ssh_head_proxy=ssh_head_proxy,
                    ssh_head_proxy_private_key=ssh_head_proxy_private_key,
                )
        except (httpx.RequestError, SSHError) as e:
            logger.debug("Gateway request failed", exc_info=True)
            raise GatewayError(repr(e))
        except GatewayError as e:
            if "already exists in service" in e.msg:
                # Pre-0.19.25 servers never mark the job as `registered`, so 0.19.25+ servers may
                # attempt to register a replica that is already registered on the gateway.
                logger.warning(
                    (
                        "%s: could not register replica in gateway: %s."
                        " NOTE: if you just updated dstack from pre-0.19.25 to 0.19.25+,"
                        " expect to see this warning once for every running service replica"
                    ),
                    fmt(job_model),
                    e.msg,
                )
            else:
                raise
    job_model.registered = True
    targets = [events.Target.from_model(job_model)]
    if gateway is not None:
        targets.append(events.Target.from_model(gateway))
    events.emit(
        session,
        "Service replica registered to receive requests",
        actor=events.SystemActor(),
        targets=targets,
    )


async def unregister_service(session: AsyncSession, run_model: RunModel):
    if run_model.gateway_id is None:  # in-server proxy
        return
    gateway, conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
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
        event_msg = "Service unregistered from gateway"
    except GatewayError as e:
        # ignore if service is not registered
        logger.warning("%s: unregistering service: %s", fmt(run_model), e)
        event_msg = f"Gateway error when unregistering service: {e}"
    except (httpx.RequestError, SSHError) as e:
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(repr(e))
    events.emit(
        session,
        event_msg,
        actor=events.SystemActor(),
        targets=[
            events.Target.from_model(run_model),
            events.Target.from_model(gateway),
        ],
    )


async def unregister_replica(session: AsyncSession, job_model: JobModel):
    if not job_model.registered:  # non-services and unregistered service replicas
        return
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(joinedload(RunModel.project))
    )
    run_model = res.unique().scalar_one()
    gateway = None
    if run_model.gateway_id is not None:
        gateway, conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
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
        except GatewayError as e:
            # ignore if replica is not registered
            logger.warning("%s: unregistering replica from service: %s", fmt(job_model), e)
        except (httpx.RequestError, SSHError) as e:
            logger.debug("Gateway request failed", exc_info=True)
            raise GatewayError(repr(e))
    job_model.registered = False
    targets = [events.Target.from_model(job_model)]
    if gateway is not None:
        targets.append(events.Target.from_model(gateway))
    events.emit(
        session,
        "Service replica unregistered from receiving requests",
        actor=events.SystemActor(),
        targets=targets,
    )


def _get_service_https(run_spec: RunSpec, configuration: GatewayConfiguration) -> bool:
    assert run_spec.configuration.type == "service"
    https = run_spec.configuration.https
    if https is None:
        https = SERVICE_HTTPS_DEFAULT
    if https == "auto":
        if configuration.certificate is None:
            return False
        if configuration.certificate.type == "acm":
            return False
        return True
    if not https:
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


async def update_service_desired_replica_count(
    session: AsyncSession,
    run_model: RunModel,
    configuration: ServiceConfiguration,
    last_scaled_at: Optional[datetime],
) -> None:
    stats = None
    if run_model.gateway_id is not None:
        _, conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
        stats = await conn.get_stats(run_model.project.name, run_model.run_name)
    replica_groups = configuration.replica_groups
    desired_replica_counts = {}
    total = 0
    prev_counts = (
        json.loads(run_model.desired_replica_counts) if run_model.desired_replica_counts else {}
    )
    if (
        prev_counts == {}
        and len(replica_groups) == 1
        and replica_groups[0].name == DEFAULT_REPLICA_GROUP_NAME
    ):
        # Special case to avoid dropping the replica count to group.count.min
        # when a 0.20.7+ server first processes a service created by a pre-0.20.7 server.
        # TODO: remove once most users upgrade to 0.20.7+.
        prev_counts = {DEFAULT_REPLICA_GROUP_NAME: run_model.desired_replica_count}
    for group in replica_groups:
        scaler = get_service_scaler(group.count, group.scaling)
        assert group.name is not None, "Group name is always set"
        group_desired = scaler.get_desired_count(
            current_desired_count=prev_counts.get(group.name, group.count.min or 0),
            stats=stats,
            last_scaled_at=last_scaled_at,
        )
        desired_replica_counts[group.name] = group_desired
        total += group_desired
    run_model.desired_replica_counts = json.dumps(desired_replica_counts)
    run_model.desired_replica_count = total
