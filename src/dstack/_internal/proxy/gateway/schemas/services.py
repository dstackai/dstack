from dstack._internal.core.models.common import CoreModel


class ServiceListReplicaItem(CoreModel):
    id: str
    ssh_head_proxy_public_key: str | None = None
    """Public key matching the head-node private key saved for this replica on the gateway.

    The server compares this with the instance's current head-node key during gateway
    synchronization and sends a replacement private key when they differ.
    `None` means no head-node private key is saved for this replica.
    """


class ServiceListItem(CoreModel):
    """The model is minimal to allow for frequent polling by the server"""

    id: str | None
    """Can temporarily be `None` for services registered before 0.21.0"""
    project_name: str
    run_name: str
    replicas: list[ServiceListReplicaItem]


class ServiceListResponse(CoreModel):
    services: list[ServiceListItem]
