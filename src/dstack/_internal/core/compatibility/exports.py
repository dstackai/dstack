from dstack._internal.core.models.common import IncludeExcludeStrDictType
from dstack._internal.server.schemas.exports import CreateExportRequest, UpdateExportRequest


def get_create_export_excludes(request: CreateExportRequest) -> IncludeExcludeStrDictType:
    excludes: IncludeExcludeStrDictType = {}
    if not request.exported_models:
        excludes["exported_models"] = True
    return excludes


def get_update_export_excludes(request: UpdateExportRequest) -> IncludeExcludeStrDictType:
    excludes: IncludeExcludeStrDictType = {}
    if not request.add_exported_models:
        excludes["add_exported_models"] = True
    if not request.remove_exported_models:
        excludes["remove_exported_models"] = True
    return excludes
