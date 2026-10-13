import httpx2 as httpx
from aiocache import cached

from dstack._internal.proxy.gateway import otel
from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.errors import UnexpectedProxyError

_AUTH_CACHE_TTL_SECONDS = 60
"""Seconds to cache allowed or denied access for each project/token pair."""


class GatewayProxyAuthProvider(BaseProxyAuthProvider):
    def __init__(self, server_client: httpx.AsyncClient) -> None:
        self._server_client = server_client

    @cached(ttl=_AUTH_CACHE_TTL_SECONDS, noself=True, skip_cache_func=lambda r: r is None)
    async def is_project_member(self, project_name: str, token: str) -> bool:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            # httpx2 is not covered by the httpx instrumentation, so trace the request manually
            with otel.server_request_span(
                "POST", "/api/projects/{project_name}/get", headers
            ) as span:
                span.set_attribute("dstack.project.name", project_name)
                resp = await self._server_client.post(
                    f"/api/projects/{project_name}/get", headers=headers
                )
                span.set_attribute("http.response.status_code", resp.status_code)
                if resp.status_code == httpx.codes.FORBIDDEN:
                    return False
                resp.raise_for_status()
        except httpx.HTTPError as e:
            raise UnexpectedProxyError(
                f"Failed requesting dstack-server to check access: {e!r}"
            ) from e
        return True
