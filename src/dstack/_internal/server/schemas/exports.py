from dstack._internal.core.models.common import CoreModel


class CreateExportRequest(CoreModel):
    name: str
    importer_projects: list[str] = []
    exported_fleets: list[str] = []
    exported_gateways: list[str] = []


class UpdateExportRequest(CoreModel):
    name: str
    add_importer_projects: list[str] = []
    remove_importer_projects: list[str] = []
    add_exported_fleets: list[str] = []
    remove_exported_fleets: list[str] = []
    add_exported_gateways: list[str] = []
    remove_exported_gateways: list[str] = []


class DeleteExportRequest(CoreModel):
    name: str
