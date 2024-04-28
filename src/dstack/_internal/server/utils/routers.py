from typing import Dict, List, Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from packaging import version

from dstack._internal.core.errors import ServerClientError


def error_detail(msg: str, code: Optional[str] = None, **kwargs) -> Dict:
    return {"msg": msg, "code": code, **kwargs}


def error_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_detail("Not found"),
    )


def error_forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_detail("Access denied"),
    )


def error_invalid_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_detail("Invalid token"),
    )


def error_bad_request(details: List[Dict]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=details,
    )


def get_server_client_error_details(error: ServerClientError) -> List[Dict]:
    if len(error.fields) == 0:
        return [error_detail(msg=error.msg, code=error.code)]
    details = []
    for field_path in error.fields:
        details.append(error_detail(msg=error.msg, code=error.code, fields=field_path))
    return details


def request_size_exceeded(request: Request, limit: int) -> bool:
    if "content-length" not in request.headers:
        return True
    content_length = int(request.headers["content-length"])
    if content_length > limit:
        return True
    return False


def check_client_server_compatibility(
    client_version: Optional[str],
    server_version: Optional[str],
) -> Optional[JSONResponse]:
    """
    Returns `JSONResponse` with error if client/server versions are incompatible.
    Returns `None` otherwise.
    """
    if client_version is None or server_version is None:
        return None
    parsed_server_version = version.parse(server_version)
    # latest allows client to bypass compatibility check (e.g. frontend)
    if client_version == "latest":
        return None
    try:
        parsed_client_version = version.parse(client_version)
    except version.InvalidVersion:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": get_server_client_error_details(
                    ServerClientError("Bad API version specified")
                )
            },
        )
    # We preserve backward-compatibility across micro releases,
    # but do not preserve forward-compatibility.
    if parsed_client_version < parsed_server_version and (
        parsed_client_version.major < parsed_server_version.major
        or parsed_client_version.minor < parsed_server_version.minor
    ):
        return error_incompatible_versions(client_version, server_version, ask_cli_update=True)
    elif parsed_client_version > parsed_server_version and (
        parsed_client_version.major > parsed_server_version.major
        or parsed_client_version.minor > parsed_server_version.minor
        or parsed_client_version.micro > parsed_server_version.micro
    ):
        return error_incompatible_versions(client_version, server_version, ask_cli_update=False)
    return None


def error_incompatible_versions(
    client_version: Optional[str],
    server_version: str,
    ask_cli_update: bool,
) -> JSONResponse:
    msg = f"The client/CLI version ({client_version}) is incompatible with the server version ({server_version})."
    if ask_cli_update:
        msg += f" Update the dstack CLI: `pip install dstack=={server_version}`."
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": get_server_client_error_details(ServerClientError(msg=msg))},
    )
