from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.gateways import Gateway


def patch_gateway(gateway: Gateway, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    if client_version < Version("0.20.25"):
        gateway.instance_id = ""
        gateway.ip_address = "\n".join(r.hostname for r in gateway.replicas if r.hostname)
        if gateway.hostname is None:
            gateway.hostname = gateway.ip_address
    if client_version == Version("0.20.25"):
        for replica in gateway.replicas:
            if replica.hostname is None:
                replica.hostname = ""
            if replica.region is None:
                replica.region = ""
            if replica.backend is None:
                replica.backend = gateway.configuration.backend
