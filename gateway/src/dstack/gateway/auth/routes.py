from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dstack.gateway.core.auth import AuthProvider, get_auth

router = APIRouter()


# TODO(egor-s): support Authorization header alternative for web browsers


@router.get("/{project}")
async def get_auth(
    project: str,
    token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    auth: AuthProvider = Depends(get_auth),
):
    if await auth.has_access(project, token.credentials):
        return {"status": "ok"}
    raise HTTPException(status_code=403)
