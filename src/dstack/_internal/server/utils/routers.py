from typing import Dict, List, Optional

from fastapi import HTTPException, status

from dstack._internal.core.errors import ServerClientError


def error_detail(msg: str, code: Optional[str] = None, **kwargs) -> Dict:
    return {"msg": msg, "code": code, **kwargs}


def raise_not_found():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_detail("Not found"),
    )


def raise_forbidden():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_detail("Access denied"),
    )


def raise_invalid_token():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_detail("Invalid token"),
    )


def raise_bad_request(details: List[Dict]):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=details,
    )


def raise_server_client_error(error: ServerClientError):
    raise_bad_request(get_server_client_error_details(error))


def get_server_client_error_details(error: ServerClientError) -> List[Dict]:
    if len(error.fields) == 0:
        return [error_detail(msg=error.msg, code=error.code)]
    details = []
    for field_path in error.fields:
        details.append(error_detail(msg=error.msg, code=error.code, fields=field_path))
    return details
