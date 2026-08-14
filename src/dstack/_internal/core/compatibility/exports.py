from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.server.schemas.exports import CreateExportRequest, UpdateExportRequest


def get_create_export_excludes(request: CreateExportRequest) -> IncludeExcludeDictType:
    excludes: IncludeExcludeDictType = {}
    return excludes


def get_update_export_excludes(request: UpdateExportRequest) -> IncludeExcludeDictType:
    excludes: IncludeExcludeDictType = {}
    return excludes
