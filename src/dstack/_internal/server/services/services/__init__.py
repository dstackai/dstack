"""
Application logic related to `type: service` runs.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    GatewayError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.configurations import (
    SERVICE_HTTPS_DEFAULT,
    EntityReference,
    ServiceConfiguration,
)
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewayStatus
from dstack._internal.core.models.runs import RunSpec, ServiceModelSpec, ServiceSpec
from dstack._internal.core.models.services import OpenAIChatModel
from dstack._internal.server import settings
from dstack._internal.server.models import GatewayModel, RunModel
from dstack._internal.server.services import events
from dstack._internal.server.services.gateways import (
    get_gateway_compute_models,
    get_gateway_configuration,
    get_project_default_gateway_model,
    get_project_gateway_model_by_reference,
)
from dstack._internal.server.services.services.options import get_service_options
from dstack._internal.utils.common import interpolate_gateway_domain
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def register_service(session: AsyncSession, run_model: RunModel, run_spec: RunSpec):
    assert isinstance(run_spec.configuration, ServiceConfiguration)

    if isinstance(run_spec.configuration.gateway, EntityReference) or isinstance(
        run_spec.configuration.gateway, str
    ):
        gateway_reference = EntityReference.parse(run_spec.configuration.gateway)
        gateway = await get_project_gateway_model_by_reference(
            session=session,
            project=run_model.project,
            ref=gateway_reference,
            load_gateway_compute=True,
            load_backend_type=True,
        )
        if gateway is None:
            raise ResourceNotExistsError(
                f"Gateway {gateway_reference.format()} does not exist"
                f" in project {run_model.project.name}"
            )
        if gateway.to_be_deleted:
            raise ResourceNotExistsError(
                f"Gateway {gateway_reference.format()} was marked for deletion"
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
        service_spec = _register_service_in_server(session, run_model, run_spec)
    else:
        raise ResourceNotExistsError(
            "This dstack-server installation forbids services without a gateway."
            " Please configure a gateway."
        )
    run_model.service_spec = service_spec.model_dump_json()


async def _register_service_in_gateway(
    session: AsyncSession, run_model: RunModel, run_spec: RunSpec, gateway: GatewayModel
) -> ServiceSpec:
    assert run_spec.configuration.type == "service"

    if not get_gateway_compute_models(gateway):
        raise ServerClientError("Gateway has no instance associated with it")

    if gateway.status != GatewayStatus.RUNNING:
        raise ServerClientError("Gateway status is not running")

    if gateway.forbid_new_services:
        raise ServerClientError("Gateway does not accept new services")

    gateway_configuration = get_gateway_configuration(gateway)

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

    gateway_https = get_gateway_https(gateway_configuration)
    gateway_protocol = "https" if gateway_https else "http"

    wildcard_domain = gateway.wildcard_domain.lstrip("*.") if gateway.wildcard_domain else None
    if wildcard_domain is None:
        raise ServerClientError("Domain is required for gateway")
    wildcard_domain = interpolate_gateway_domain(
        domain=wildcard_domain,
        run_project_name=run_model.project.name,
        exception_type=GatewayError,
    )
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
    events.emit(
        session,
        "Service assigned to gateway",
        actor=events.SystemActor(),
        targets=[events.Target.from_model(run_model), events.Target.from_model(gateway)],
    )
    return service_spec


def _register_service_in_server(
    session: AsyncSession, run_model: RunModel, run_spec: RunSpec
) -> ServiceSpec:
    assert run_spec.configuration.type == "service"
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
    events.emit(
        session,
        "Service assigned to run without a gateway",
        actor=events.SystemActor(),
        targets=[events.Target.from_model(run_model)],
    )
    return _get_service_spec(
        configuration=run_spec.configuration,
        service_url=service_url,
        model_url=model_url,
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


def should_configure_service_https_on_gateway(
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


def get_gateway_https(configuration: GatewayConfiguration) -> bool:
    if configuration.certificate is not None and configuration.certificate.type == "acm":
        return False
    if configuration.certificate is not None and configuration.certificate.type == "lets-encrypt":
        return True
    return False
