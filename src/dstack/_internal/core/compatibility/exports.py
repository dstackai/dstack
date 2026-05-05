from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.server.schemas.exports import CreateExportRequest, UpdateExportRequest


def get_create_export_excludes(request: CreateExportRequest) -> IncludeExcludeDictType:
    excludes: IncludeExcludeDictType = {}
    if not request.exported_gateways:
        excludes["exported_gateways"] = True
    return excludes


def get_update_export_excludes(request: UpdateExportRequest) -> IncludeExcludeDictType:
    excludes: IncludeExcludeDictType = {}
    if not request.add_exported_gateways:
        excludes["add_exported_gateways"] = True
    if not request.remove_exported_gateways:
        excludes["remove_exported_gateways"] = True
    return excludes
