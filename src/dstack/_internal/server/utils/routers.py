from typing import Dict, Optional

from fastapi import HTTPException, status


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
