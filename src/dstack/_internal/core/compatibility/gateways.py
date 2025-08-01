from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewaySpec


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


def _get_gateway_configuration_excludes(
    configuration: GatewayConfiguration,
) -> IncludeExcludeDictType:
    configuration_excludes: IncludeExcludeDictType = {}
    if configuration.tags is None:
        configuration_excludes["tags"] = True
    return configuration_excludes
