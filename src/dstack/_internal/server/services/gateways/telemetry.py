"""OpenTelemetry settings of gateway replicas."""

from collections.abc import Mapping
from typing import Optional, Union

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
    """Checks that the secrets referenced in the OpenTelemetry config exist in `project`."""
    if configuration.otel is None:
        return
    secrets = await get_project_secrets_mapping(session=session, project=project)
    try:
        _interpolate_otel_config(configuration.otel, secrets)
    except InterpolatorError as e:
        raise ServerClientError(f"Invalid gateway otel configuration: {e}")


def get_gateway_replica_otel_settings(
    gateway_model: GatewayModel,
    gateway_configuration: GatewayConfiguration,
    replica_model: GatewayReplicaModel,
    secrets: Mapping[str, str],
) -> Optional[OTelSettings]:
    """
    Returns the OpenTelemetry settings for the gateway replica app,
    or None if OpenTelemetry is disabled for the gateway.

    Args:
        secrets: The secrets of the gateway's project. Never use the secrets of
            projects that import the gateway.

    Requires `gateway_model.project` and `gateway_model.backend` to be loaded.
    """
    otel = gateway_configuration.otel
    if otel is None or not (otel.traces or otel.logs or otel.metrics):
        return None
    try:
        endpoint, headers = _interpolate_otel_config(otel, secrets)
    except InterpolatorError as e:
        # E.g., a referenced secret was deleted. The error does not contain secret values.
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


def _interpolate_otel_config(
    otel: GatewayOTelConfig, secrets: Mapping[str, str]
) -> tuple[str, dict[str, str]]:
    interpolate = VariablesInterpolator({"secrets": secrets}).interpolate_or_error
    endpoint = interpolate(otel.endpoint)
    headers = {name: interpolate(value) for name, value in (otel.headers or {}).items()}
    return endpoint, headers


def _get_resource_attributes(
    gateway_model: GatewayModel, replica_model: GatewayReplicaModel
) -> dict[str, Union[str, int]]:
    attributes: dict[str, Union[str, int]] = {
        # Distinguishes replicas: without it, metrics pushed by multiple
        # gateway replicas collapse into the same series, corrupting counters
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
