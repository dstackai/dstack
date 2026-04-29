import uuid

from dstack._internal.core.models.common import CoreModel


class ExportImport(CoreModel):
    project_name: str


class ExportedFleet(CoreModel):
    id: uuid.UUID
    name: str


class ExportedGateway(CoreModel):
    id: uuid.UUID
    name: str


class Export(CoreModel):
    id: uuid.UUID
    name: str
    imports: list[ExportImport]
    exported_fleets: list[ExportedFleet]
    exported_gateways: list[ExportedGateway]
