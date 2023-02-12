from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials

from dstack.hub.repository.user import UserManager

router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer()


@router.get("/validate")
async def validate(authorization: HTTPAuthorizationCredentials = Depends(security)):
    user = await UserManager.get_user_by_token(authorization.credentials)
    if not (user is None):
        return
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token is invalid",
        )
