import re
from collections.abc import Mapping
from typing import Optional, Union
from urllib.parse import urlsplit

from dstack._internal.core.models.gateways import GatewayConfiguration, GatewayOTelConfig
from dstack._internal.proxy.gateway.models import OTelSettings
from dstack._internal.server import settings
from dstack._internal.server.models import GatewayModel, GatewayReplicaModel
from dstack._internal.server.services.logging import fmt
from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def get_gateway_replica_otel_settings(
    gateway_model: GatewayModel,
    gateway_configuration: GatewayConfiguration,
    replica_model: GatewayReplicaModel,
    secrets: Mapping[str, str],
) -> Optional[OTelSettings]:
    otel = gateway_configuration.otel
    if otel is None or not is_gateway_otel_enabled(otel):
        return None
    try:
        endpoint, headers = resolve_gateway_otel_config(otel, secrets)
    except InvalidGatewayOTelConfigError as e:
        # E.g., a referenced secret was deleted or changed to an invalid value
        logger.warning("%s: cannot enable OpenTelemetry: %s", fmt(replica_model), e)
        return None
    return OTelSettings(
        traces_enabled=otel.traces,
        logs_enabled=otel.logs,
        metrics_enabled=otel.metrics,
        endpoint=endpoint,
        headers=headers,
        traces_sample_rate=otel.traces_sample_rate,
        traces_auth_sample_rate=otel.traces_auth_sample_rate,
        resource_attributes=_get_resource_attributes(gateway_model, replica_model),
    )


def is_gateway_otel_enabled(otel: GatewayOTelConfig) -> bool:
    return otel.traces or otel.logs or otel.metrics


class InvalidGatewayOTelConfigError(ValueError):
    """The message is shown to users and must not contain secret values."""


def resolve_gateway_otel_config(
    otel: GatewayOTelConfig, secrets: Mapping[str, str]
) -> tuple[str, dict[str, str]]:
    """Returns the endpoint and headers with secrets interpolated."""
    interpolate = VariablesInterpolator({"secrets": secrets}).interpolate_or_error
    try:
        endpoint = interpolate(otel.endpoint)
        headers = {name: interpolate(value) for name, value in (otel.headers or {}).items()}
    except InterpolatorError as e:
        raise InvalidGatewayOTelConfigError(str(e)) from None
    _validate_endpoint(endpoint)
    for name, value in headers.items():
        _validate_header(name, value)
    return endpoint, headers


def _validate_endpoint(endpoint: str) -> None:
    # Checked explicitly, since urlsplit silently strips tabs and line breaks
    if any(c.isspace() or not c.isprintable() for c in endpoint):
        raise InvalidGatewayOTelConfigError(
            "endpoint must not contain whitespace or control characters"
        )
    try:
        url = urlsplit(endpoint)
        url.port  # Raises on invalid ports
    except ValueError:
        raise InvalidGatewayOTelConfigError("endpoint must be a valid URL") from None
    if url.scheme not in ("http", "https") or not url.hostname:
        raise InvalidGatewayOTelConfigError("endpoint must be an http:// or https:// URL")
    # Signal paths are appended to the endpoint and would end up in the query or fragment
    if "?" in endpoint or "#" in endpoint:
        raise InvalidGatewayOTelConfigError("endpoint must not contain a query or fragment")


# RFC 9110 token. Use with fullmatch
_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")


def _validate_header(name: str, value: str) -> None:
    if not _HEADER_NAME_RE.fullmatch(name):
        raise InvalidGatewayOTelConfigError(f"invalid header name {name!r}")
    if not (value.isprintable() and value == value.strip() and all(ord(c) < 256 for c in value)):
        raise InvalidGatewayOTelConfigError(f"header {name!r} has an invalid value")


def _get_resource_attributes(
    gateway_model: GatewayModel, replica_model: GatewayReplicaModel
) -> dict[str, Union[str, int]]:
    attributes: dict[str, Union[str, int]] = {
        "service.instance.id": str(replica_model.id),
        "dstack.gateway.replica.num": replica_model.replica_num,
        "deployment.environment.name": settings.SERVER_ENVIRONMENT,
        "dstack.project.name": gateway_model.project.name,
        "dstack.gateway.name": gateway_model.name,
        "dstack.backend": gateway_model.backend.type.value,
    }
    if replica_model.ip_address is not None:
        attributes["host.name"] = replica_model.ip_address
    if replica_model.region is not None:
        attributes["cloud.region"] = replica_model.region
    return attributes
