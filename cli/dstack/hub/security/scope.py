from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from starlette.requests import Request

from dstack.hub.repository.user import UserManager


class Scope:
    _scope = ""

    def __init__(self, scope: str) -> None:
        self._scope = scope

    async def __call__(
        self, request: Request, token: HTTPAuthorizationCredentials = Security(HTTPBearer())
    ):
        user = await UserManager.get_user_by_token(token.credentials)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token is invalid",
            )
        access = await UserManager.scope(user=user, scope=self._scope)
        if not access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied",
            )
