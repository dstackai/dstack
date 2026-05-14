from dstack._internal.core.models.common import CoreModel


class CreateExportRequest(CoreModel):
    name: str
    is_global: bool = False
    importer_projects: list[str] = []
    exported_fleets: list[str] = []
    exported_gateways: list[str] = []


class UpdateExportRequest(CoreModel):
    name: str
    set_global: bool = False
    unset_global: bool = False
    add_importer_projects: list[str] = []
    remove_importer_projects: list[str] = []
    add_exported_fleets: list[str] = []
    remove_exported_fleets: list[str] = []
    add_exported_gateways: list[str] = []
    remove_exported_gateways: list[str] = []


class DeleteExportRequest(CoreModel):
    name: str
