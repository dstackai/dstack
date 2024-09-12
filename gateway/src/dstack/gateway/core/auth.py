import logging
from functools import lru_cache

import httpx
from aiocache import cached
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dstack.gateway.core.multi_client import dstack_server_client

logger = logging.getLogger(__name__)


class AuthProvider:
    @cached(ttl=60, noself=True, skip_cache_func=lambda r: r is None)
    async def has_access(self, project: str, token: str) -> bool | None:
        """True - yes, False - no, None - failed checking"""

        try:
            resp = await dstack_server_client.post(
                f"/api/projects/{project}/get",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == httpx.codes.FORBIDDEN:
                return False
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("Failed requesting dstack-server to check access: %r", e)
            return None
        return True


@lru_cache()
def get_auth() -> AuthProvider:
    return AuthProvider()


async def access_to_project_required(
    project: str,
    auth: AuthProvider = Depends(get_auth),
    token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
) -> None:
    has_access = await auth.has_access(project, token.credentials)
    if has_access is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal error when checking authorization. Try again later",
        )
    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
