from typing import Dict

from dstack._internal.core.models.gateways import GatewayConfiguration, GatewaySpec


def get_gateway_spec_excludes(gateway_spec: GatewaySpec) -> Dict:
    """
    Returns `gateway_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes = {}
    spec_excludes["configuration"] = _get_gateway_configuration_excludes(
        gateway_spec.configuration
    )
    return spec_excludes


def get_create_gateway_excludes(configuration: GatewayConfiguration) -> Dict:
    """
    Returns an exclude mapping to exclude certain fields from the create gateway request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    create_gateway_excludes = {}
    create_gateway_excludes["configuration"] = _get_gateway_configuration_excludes(configuration)
    return create_gateway_excludes


def _get_gateway_configuration_excludes(configuration: GatewayConfiguration) -> Dict:
    configuration_excludes = {}
    if configuration.tags is None:
        configuration_excludes["tags"] = True
    return configuration_excludes
