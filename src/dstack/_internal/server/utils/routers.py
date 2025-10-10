from typing import Any, Dict, List, Optional

import orjson
from fastapi import HTTPException, Request, Response, status
from packaging import version

from dstack._internal.core.errors import ServerClientError, ServerClientErrorCode
from dstack._internal.core.models.common import CoreModel
from dstack._internal.utils.json_utils import get_orjson_default_options, orjson_default


class CustomORJSONResponse(Response):
    """
    Custom JSONResponse that uses orjson for serialization.

    It's recommended to return this class from routers directly instead of
    returning pydantic models to avoid the FastAPI's jsonable_encoder overhead.
    See https://fastapi.tiangolo.com/advanced/custom-response/#use-orjsonresponse.

    Beware that FastAPI skips model validation when responses are returned directly.
    If serialization needs to be modified, override `dict()` instead of adding validators.
    """

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return orjson.dumps(
            content,
            option=get_orjson_default_options(),
            default=orjson_default,
        )


class BadRequestDetailsModel(CoreModel):
    code: Optional[ServerClientErrorCode] = ServerClientErrorCode.UNSPECIFIED_ERROR
    msg: str


class BadRequestErrorModel(CoreModel):
    detail: BadRequestDetailsModel


class AccessDeniedDetailsModel(CoreModel):
    code: Optional[str] = None
    msg: str = "Access denied"


class AccessDeniedErrorModel(CoreModel):
    detail: AccessDeniedDetailsModel


def get_base_api_additional_responses() -> Dict:
    """
    Returns additional responses for the OpenAPI docs relevant to all API endpoints.
    The endpoints may override responses to make them as specific as possible.
    E.g. an endpoint may specify which error codes it may return in `code`.
    """
    return {
        400: get_bad_request_additional_response(),
        403: get_access_denied_additional_response(),
    }


def get_bad_request_additional_response() -> Dict:
    return {
        "description": "Bad request",
        "model": BadRequestErrorModel,
    }


def get_access_denied_additional_response() -> Dict:
    return {
        "description": "Access denied",
        "model": AccessDeniedErrorModel,
    }


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


def get_request_size(request: Request) -> int:
    if "content-length" not in request.headers:
        return 0
    return int(request.headers["content-length"])


def check_client_server_compatibility(
    client_version: Optional[str],
    server_version: Optional[str],
) -> Optional[CustomORJSONResponse]:
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
        return CustomORJSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": get_server_client_error_details(
                    ServerClientError("Bad API version specified")
                )
            },
        )
    # We preserve full client backward compatibility across patch releases.
    # Server is always partially backward-compatible (so no check).
    if parsed_client_version > parsed_server_version and (
        parsed_client_version.major > parsed_server_version.major
        or parsed_client_version.minor > parsed_server_version.minor
    ):
        return error_incompatible_versions(client_version, server_version, ask_cli_update=False)
    return None


def error_incompatible_versions(
    client_version: Optional[str],
    server_version: str,
    ask_cli_update: bool,
) -> CustomORJSONResponse:
    msg = f"The client/CLI version ({client_version}) is incompatible with the server version ({server_version})."
    if ask_cli_update:
        msg += f" Update the dstack CLI: `pip install dstack=={server_version}`."
    return CustomORJSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": get_server_client_error_details(ServerClientError(msg=msg))},
    )
