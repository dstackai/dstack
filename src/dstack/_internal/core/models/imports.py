import uuid

from dstack._internal.core.models.common import CoreModel


class ImportExportedFleet(CoreModel):
    id: uuid.UUID
    name: str


class ImportExportedGateway(CoreModel):
    id: uuid.UUID
    name: str


class ImportExport(CoreModel):
    id: uuid.UUID
    name: str
    project_name: str
    exported_fleets: list[ImportExportedFleet]
    exported_gateways: list[ImportExportedGateway] = []


class Import(CoreModel):
    id: uuid.UUID
    export: ImportExport
