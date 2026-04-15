"""
Application logic related to `type: service` runs.
"""

from functools import partial
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    GatewayError,
    ResourceNotExistsError,
    ServerClientError,
    SSHError,
)
from dstack._internal.core.models.configurations import (
    SERVICE_HTTPS_DEFAULT,
    ServiceConfiguration,
)
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewayStatus
from dstack._internal.core.models.routers import (
    AnyServiceRouterConfig,
    RouterType,
    SGLangServiceRouterConfig,
)
from dstack._internal.core.models.runs import RunSpec, ServiceModelSpec, ServiceSpec
from dstack._internal.core.models.services import OpenAIChatModel
from dstack._internal.proxy.gateway.const import SERVICE_ALREADY_REGISTERED_ERROR_TEMPLATE
from dstack._internal.server import settings
from dstack._internal.server.models import GatewayModel, RunModel
from dstack._internal.server.services import events
from dstack._internal.server.services.gateways import (
    get_gateway_configuration,
    get_or_add_gateway_connection,
    get_project_default_gateway_model,
    get_project_gateway_model_by_name,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.services.options import get_service_options
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def register_service(session: AsyncSession, run_model: RunModel, run_spec: RunSpec):
    assert isinstance(run_spec.configuration, ServiceConfiguration)

    if isinstance(run_spec.configuration.gateway, str):
        gateway = await get_project_gateway_model_by_name(
            session=session,
            project=run_model.project,
            name=run_spec.configuration.gateway,
            load_gateway_compute=True,
            load_backend_type=True,
        )
        if gateway is None:
            raise ResourceNotExistsError(
                f"Gateway {run_spec.configuration.gateway} does not exist"
            )
        if gateway.to_be_deleted:
            raise ResourceNotExistsError(
                f"Gateway {run_spec.configuration.gateway} was marked for deletion"
            )
    elif run_spec.configuration.gateway == False:
        gateway = None
    else:
        gateway = await get_project_default_gateway_model(
            session=session,
            project=run_model.project,
            load_gateway_compute=True,
            load_backend_type=True,
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

    has_replica_group_router = any(
        g.router is not None for g in run_spec.configuration.replica_groups
    )
    if has_replica_group_router and _gateway_has_sglang_router(gateway_configuration):
        raise ServerClientError(
            "A replica-group `router:` cannot be used with a gateway that has router configuration."
        )

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

    configure_service_https = _should_configure_service_https_on_gateway(
        run_spec, gateway_configuration
    )
    show_service_https = _should_show_service_https(run_spec, gateway_configuration)
    service_protocol = "https" if show_service_https else "http"

    if (
        not show_service_https
        and gateway_configuration.certificate is not None
        and gateway_configuration.certificate.type == "acm"
    ):
        # SSL termination is done globally at load balancer so cannot runs only some services via http.
        raise ServerClientError(
            "Cannot run HTTP service on gateway with ACM certificates configured"
        )

    if show_service_https and gateway_configuration.certificate is None:
        raise ServerClientError(
            "Cannot run HTTPS service on gateway with no SSL certificates configured"
        )

    router = _build_service_router_config(gateway_configuration, run_spec.configuration)

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
    service_spec = _get_service_spec(
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
                service_https=configure_service_https,
                gateway_https=gateway_https,
                auth=run_spec.configuration.auth,
                client_max_body_size=settings.DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE,
                options=service_spec.options,
                rate_limits=run_spec.configuration.rate_limits,
                ssh_private_key=run_model.project.ssh_private_key,
                has_router_replica=has_replica_group_router,
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
    return _get_service_spec(
        configuration=run_spec.configuration,
        service_url=service_url,
        model_url=model_url,
    )


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


def _get_service_spec(
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


def _should_configure_service_https_on_gateway(
    run_spec: RunSpec, configuration: GatewayConfiguration
) -> bool:
    """
    Returns `True` if the gateway needs to serve the service with HTTPS.
    May be `False` for HTTPS services, e.g. SSL termination is done on a load balancer.
    """
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


def _should_show_service_https(run_spec: RunSpec, configuration: GatewayConfiguration) -> bool:
    """
    Returns `True` if the service needs to be accessed via https://.
    """
    assert run_spec.configuration.type == "service"
    https = run_spec.configuration.https
    if https is None:
        https = SERVICE_HTTPS_DEFAULT
    if https == "auto":
        if configuration.certificate is None:
            return False
        return True
    return https


def _get_gateway_https(configuration: GatewayConfiguration) -> bool:
    if configuration.certificate is not None and configuration.certificate.type == "acm":
        return False
    if configuration.certificate is not None and configuration.certificate.type == "lets-encrypt":
        return True
    return False
