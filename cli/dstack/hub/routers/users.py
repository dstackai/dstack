from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials

from dstack.hub.models import UserInfo
from dstack.hub.repository.user import UserManager
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/users", tags=["users"])

security = HTTPBearer()


@router.get("/me", response_model=UserInfo, dependencies=[Depends(Scope("hub:list:read"))])
async def info(authorization: HTTPAuthorizationCredentials = Depends(security)) -> UserInfo:
    user = await UserManager.get_user_by_token(authorization.credentials)
    return UserInfo(user_name=user.name)
