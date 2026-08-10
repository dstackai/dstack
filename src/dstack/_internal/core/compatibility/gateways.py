from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.core.models.gateways import (
    ApplyGatewayPlanInput,
    GatewayConfiguration,
    GatewaySpec,
)
from dstack._internal.server.schemas.gateways import SetDefaultGatewayRequest


def get_apply_plan_excludes(plan_input: ApplyGatewayPlanInput) -> IncludeExcludeDictType:
    apply_plan_excludes: IncludeExcludeDictType = {}
    if plan_input.current_resource is not None:
        # `Gateway.backend` and `Gateway.region` are deprecated and never set since 0.21.
        # Not sending them lets 0.22 drop the fields without breaking 0.21 clients.
        apply_plan_excludes["current_resource"] = {"backend": True, "region": True}
    return {"plan": apply_plan_excludes}


def get_gateway_spec_excludes(gateway_spec: GatewaySpec) -> IncludeExcludeDictType:
    """
    Returns `gateway_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: IncludeExcludeDictType = {}
    spec_excludes["configuration"] = _get_gateway_configuration_excludes(
        gateway_spec.configuration
    )
    return spec_excludes


def get_create_gateway_excludes(configuration: GatewayConfiguration) -> IncludeExcludeDictType:
    """
    Returns an exclude mapping to exclude certain fields from the create gateway request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    create_gateway_excludes: IncludeExcludeDictType = {}
    create_gateway_excludes["configuration"] = _get_gateway_configuration_excludes(configuration)
    return create_gateway_excludes


def get_set_default_gateway_excludes(request: SetDefaultGatewayRequest) -> IncludeExcludeDictType:
    excludes: IncludeExcludeDictType = {}
    return excludes


def _get_gateway_configuration_excludes(
    configuration: GatewayConfiguration,
) -> IncludeExcludeDictType:
    configuration_excludes: IncludeExcludeDictType = {}
    return configuration_excludes
