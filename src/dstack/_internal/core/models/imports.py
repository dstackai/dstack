import uuid
from typing import Optional

from dstack._internal.core.models.common import CoreModel


class ImportExportedFleet(CoreModel):
    id: uuid.UUID
    name: str


class ImportExportedGateway(CoreModel):
    id: uuid.UUID
    name: str


class ImportExportedModel(CoreModel):
    name: str
    base_url: Optional[str] = None
    """`base_url` is the importer project's model endpoint on the gateway that serves the model.
    `None` while no service of the exporter project serves the model to importer projects.
    """


class ImportExport(CoreModel):
    id: uuid.UUID
    name: str
    project_name: str
    exported_fleets: list[ImportExportedFleet]
    exported_gateways: list[ImportExportedGateway] = []
    exported_models: list[ImportExportedModel] = []


class Import(CoreModel):
    id: uuid.UUID
    export: ImportExport


class ListImportsResponse(CoreModel):
    imports: list[Import]
    warnings: list[str] = []
