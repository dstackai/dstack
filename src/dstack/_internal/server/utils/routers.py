from typing import Any, Dict, List, Optional

import packaging.version
from fastapi import HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from pydantic_core import to_json

from dstack._internal.core.errors import ServerClientError, ServerClientErrorCode
from dstack._internal.core.models.common import CoreModel
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.version import parse_version

logger = get_logger(__name__)


class CustomStaticFiles(StaticFiles):
    """
    StaticFiles raises AssertionError on "websocket" scope type,
    but starlette's Mount() matches both "http" and "websocket".
    So a custom ASGI app is needed to reject WebSocket requests gracefully.

    See: https://github.com/dstackai/dstack/issues/4061
    """

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close"})  # Reject the handshake
            return
        await super().__call__(scope, receive, send)


class CustomJSONResponse(Response):
    """
    JSONResponse backed by pydantic's own Rust serializer.

    It's recommended to return this class from routers directly instead of
    returning pydantic models to avoid the FastAPI's jsonable_encoder overhead.
    See https://fastapi.tiangolo.com/advanced/custom-response/#use-orjsonresponse.

    Beware that FastAPI skips model validation when responses are returned directly.
    If serialization needs to be modified, add a `@field_serializer`/`@model_serializer`
    instead of adding validators.
    """

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        # `content` is a model, a list of models, or a plain dict (the `server/compatibility/`
        # patches mutate models in place, but some routers do assemble dicts), so it has to be
        # serialized generically rather than through one model's `model_dump_json`.
        return to_json(content, fallback=_fallback)


def _fallback(obj: Any) -> str:
    """
    Last resort for a type `to_json` cannot serialize.

    Returning a string keeps one unexpected value from turning the whole response into a 500, but
    it also puts a `repr` on the wire where the client expects real data, so it must not pass
    silently: the fix is a `@field_serializer` on the field that produced it.
    """
    logger.error(
        "Response contains a value of non-serializable type %s. Add a serializer for it.",
        type(obj).__name__,
    )
    return str(obj)


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


def get_client_version(request: Request) -> Optional[packaging.version.Version]:
    """
    FastAPI dependency that returns the dstack client version or None if the version is latest/dev.
    """

    version = request.headers.get("x-api-version")
    if version is None:
        return None
    try:
        return parse_version(version)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[error_detail(str(e))],
        )


def check_client_server_compatibility(
    client_version: Optional[packaging.version.Version],
    server_version: Optional[str],
) -> None:
    """
    Raise HTTP exception if the client is incompatible with the server.
    """
    if client_version is None or server_version is None:
        return None
    parsed_server_version = parse_version(server_version)
    if parsed_server_version is None:
        return None
    # We preserve full client backward compatibility across patch releases.
    # Server is always partially backward-compatible (so no check).
    if client_version > parsed_server_version and (
        client_version.major > parsed_server_version.major
        or client_version.minor > parsed_server_version.minor
    ):
        msg = f"The client/CLI version ({client_version}) is incompatible with the server version ({server_version})."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_server_client_error_details(ServerClientError(msg=msg)),
        )
    return None
