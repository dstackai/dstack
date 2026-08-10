from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.gateways import (
    Gateway,
    GatewayConfiguration,
    GatewayPlan,
    GatewaySpec,
)


def patch_gateway_spec_in_request(spec: GatewaySpec, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    if client_version < Version("0.21.1") and spec.configuration.default is False:
        # Pre-0.21.1 clients send `default=false` both when `default` was omitted and when it was
        # set to `false` explicitly. Assume it was omitted, which is more common and more useful.
        spec.configuration.default = None


def patch_gateway(gateway: Gateway, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    _patch_gateway_configuration(gateway.configuration, client_version)
    if client_version < Version("0.20.25"):
        gateway.instance_id = ""
        gateway.ip_address = "\n".join(r.hostname for r in gateway.replicas if r.hostname)
        if gateway.hostname is None:
            gateway.hostname = gateway.ip_address
    if client_version in (Version("0.20.25"), Version("0.20.26")):
        for replica in gateway.replicas:
            if replica.hostname is None:
                replica.hostname = ""
            if replica.region is None:
                replica.region = ""
            if replica.backend is None:
                replica.backend = gateway.configuration.backend


def patch_gateway_plan(plan: GatewayPlan, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    _patch_gateway_configuration(plan.spec.configuration, client_version)
    _patch_gateway_configuration(plan.effective_spec.configuration, client_version)
    if plan.current_resource is not None:
        patch_gateway(plan.current_resource, client_version)


def _patch_gateway_configuration(
    configuration: GatewayConfiguration, client_version: Optional[Version]
):
    if client_version is None:
        return
    if client_version < Version("0.21.1") and configuration.default is None:
        configuration.default = False
