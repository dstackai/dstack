import httpx
from aiocache import cached

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.errors import UnexpectedProxyError


class GatewayProxyAuthProvider(BaseProxyAuthProvider):
    def __init__(self, server_client: httpx.AsyncClient) -> None:
        self._server_client = server_client

    @cached(ttl=60, noself=True, skip_cache_func=lambda r: r is None)
    async def is_project_member(self, project_name: str, token: str) -> bool:
        try:
            resp = await self._server_client.post(
                f"/api/projects/{project_name}/get",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == httpx.codes.FORBIDDEN:
                return False
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise UnexpectedProxyError(
                f"Failed requesting dstack-server to check access: {e!r}"
            ) from e
        return True
