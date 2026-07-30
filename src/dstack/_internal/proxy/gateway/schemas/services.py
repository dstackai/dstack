from dstack._internal.core.models.common import CoreModel


class ServiceListReplicaItem(CoreModel):
    id: str


class ServiceListItem(CoreModel):
    """The model is minimal to allow for frequent polling by the server"""

    id: str | None
    """Can temporarily be `None` for services registered before 0.21.0"""
    project_name: str
    run_name: str
    replicas: list[ServiceListReplicaItem]


class ServiceListResponse(CoreModel):
    services: list[ServiceListItem]
