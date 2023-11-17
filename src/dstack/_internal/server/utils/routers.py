from typing import Dict, List, Optional

from fastapi import HTTPException, Request, Response, status

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
