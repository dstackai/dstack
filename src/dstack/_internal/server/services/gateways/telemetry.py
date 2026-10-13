import re
from collections.abc import Mapping
from typing import Optional, Union
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewayOTelConfig
from dstack._internal.proxy.gateway.models import OTelSettings
from dstack._internal.server import settings
from dstack._internal.server.models import GatewayModel, GatewayReplicaModel, ProjectModel
from dstack._internal.server.services.secrets import get_project_secrets_mapping
from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def validate_gateway_otel_config(
    session: AsyncSession, project: ProjectModel, configuration: GatewayConfiguration
) -> None:
    if configuration.otel is None:
        return
    secrets = await get_project_secrets_mapping(session=session, project=project)
    try:
        _resolve_otel_config(configuration.otel, secrets)
    except (InterpolatorError, _InvalidOTelConfigError) as e:
        raise ServerClientError(f"Invalid gateway otel configuration: {e}")


def get_gateway_replica_otel_settings(
    gateway_model: GatewayModel,
    gateway_configuration: GatewayConfiguration,
    replica_model: GatewayReplicaModel,
    secrets: Mapping[str, str],
) -> Optional[OTelSettings]:
    otel = gateway_configuration.otel
    if otel is None or not (otel.traces or otel.logs or otel.metrics):
        return None
    try:
        endpoint, headers = _resolve_otel_config(otel, secrets)
    except (InterpolatorError, _InvalidOTelConfigError) as e:
        # E.g., a referenced secret was deleted or changed to an invalid value
        logger.warning(
            "Cannot enable OpenTelemetry on gateway replica %s: %s", replica_model.id, e
        )
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


class _InvalidOTelConfigError(ValueError):
    """The message is shown to users and must not contain secret values."""


def _resolve_otel_config(
    otel: GatewayOTelConfig, secrets: Mapping[str, str]
) -> tuple[str, dict[str, str]]:
    interpolate = VariablesInterpolator({"secrets": secrets}).interpolate_or_error
    endpoint = interpolate(otel.endpoint)
    _validate_endpoint(endpoint)
    headers = {}
    for name, value in (otel.headers or {}).items():
        headers[name] = interpolate(value)
        _validate_header(name, headers[name])
    return endpoint, headers


def _validate_endpoint(endpoint: str) -> None:
    # Checked explicitly, since urlsplit silently strips tabs and line breaks
    if any(c.isspace() or not c.isprintable() for c in endpoint):
        raise _InvalidOTelConfigError("endpoint must not contain whitespace or control characters")
    try:
        url = urlsplit(endpoint)
        url.port  # Raises on invalid ports
    except ValueError:
        raise _InvalidOTelConfigError("endpoint must be a valid URL") from None
    if url.scheme not in ("http", "https") or not url.hostname:
        raise _InvalidOTelConfigError("endpoint must be an http:// or https:// URL")


# RFC 9110, Latin-1 only, without leading or trailing whitespace. Use with fullmatch
_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_HEADER_VALUE_RE = re.compile(
    r"(?:[\x21-\x7e\x80-\xff](?:[\t\x20-\x7e\x80-\xff]*[\x21-\x7e\x80-\xff])?)?"
)


def _validate_header(name: str, value: str) -> None:
    if not _HEADER_NAME_RE.fullmatch(name):
        raise _InvalidOTelConfigError(f"invalid header name {name!r}")
    if not _HEADER_VALUE_RE.fullmatch(value):
        raise _InvalidOTelConfigError(
            f"header {name!r} has an invalid value,"
            " e.g. it contains line breaks or leading or trailing whitespace"
        )


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
