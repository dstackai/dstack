from packaging.version import Version

from dstack._internal.core.models.exports import Export, ListExportsResponse


def patch_list_exports_response(
    response: ListExportsResponse, client_version: Version | None
) -> ListExportsResponse | list[Export]:
    if client_version is not None and client_version < Version("0.22.0"):
        return response.exports
    return response
