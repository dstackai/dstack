import logging
from functools import lru_cache

import httpx
from aiocache import cached

from dstack.gateway.common import AsyncClientWrapper

DSTACK_SERVER_TUNNEL_PORT = 8001
logger = logging.getLogger(__name__)


class AuthProvider:
    def __init__(self):
        self.client = AsyncClientWrapper(base_url=f"http://localhost:{DSTACK_SERVER_TUNNEL_PORT}")

    @cached(ttl=60, noself=True)
    async def has_access(self, project: str, token: str) -> bool:
        try:
            resp = await self.client.post(
                f"/api/projects/{project}/get",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return True
        except httpx.RequestError as e:
            logger.debug("Failed to check access: %r", e)
        return False


@lru_cache()
def get_auth() -> AuthProvider:
    return AuthProvider()
