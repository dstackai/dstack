from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.gateways import Gateway


def patch_gateway(gateway: Gateway, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    if client_version < Version("0.20.25") and len(gateway.replicas) < 2:
        gateway.instance_id = ""
        gateway.ip_address = gateway.replicas[0].hostname if gateway.replicas else ""
        if gateway.hostname is None:
            gateway.hostname = gateway.ip_address
