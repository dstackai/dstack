from dstack._internal.core.models.common import IncludeExcludeStrDictType
from dstack._internal.server.schemas.exports import CreateExportRequest, UpdateExportRequest


def get_create_export_excludes(request: CreateExportRequest) -> IncludeExcludeStrDictType:
    excludes: IncludeExcludeStrDictType = {}
    return excludes


def get_update_export_excludes(request: UpdateExportRequest) -> IncludeExcludeStrDictType:
    excludes: IncludeExcludeStrDictType = {}
    return excludes
