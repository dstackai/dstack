from packaging.version import Version

from dstack._internal.core.models.imports import Import, ListImportsResponse


def patch_list_imports_response(
    response: ListImportsResponse, client_version: Version | None
) -> ListImportsResponse | list[Import]:
    if client_version is not None and client_version < Version("0.22.0"):
        return response.imports
    return response
