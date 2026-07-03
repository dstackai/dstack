from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.gateways import Gateway, GatewayPlan


def patch_gateway(gateway: Gateway, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
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
    if plan.current_resource is not None:
        patch_gateway(plan.current_resource, client_version)
