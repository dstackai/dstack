import uuid

import httpx2 as httpx
from aiocache import cached
from pydantic import ValidationError

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.errors import UnexpectedProxyError
from dstack._internal.proxy.lib.schemas.usage import AuthorizedSubject

_AUTH_CACHE_TTL_SECONDS = 60
"""Seconds to cache allowed or denied access for each project/token pair."""


class GatewayProxyAuthProvider(BaseProxyAuthProvider):
    def __init__(self, server_client: httpx.AsyncClient) -> None:
        self._server_client = server_client
        self._cache_namespace = uuid.uuid4().hex

    @cached(
        ttl=_AUTH_CACHE_TTL_SECONDS,
        key_builder=lambda f, self, project, token: repr((self._cache_namespace, project, token)),
        skip_cache_func=lambda r: r is None,
    )
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

    async def resolve_subject(self, project_name: str, token: str) -> AuthorizedSubject | None:
        return await self._resolve_subject(project_name, token)

    @cached(
        ttl=_AUTH_CACHE_TTL_SECONDS,
        key_builder=lambda f, self, project, token: repr((self._cache_namespace, project, token)),
        skip_cache_func=lambda result: result is None,
    )
    async def _resolve_subject(self, project_name: str, token: str) -> AuthorizedSubject | None:
        try:
            response = await self._server_client.post(
                f"/api/projects/{project_name}/authorize_proxy",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code in (401, 403, 404, 405):
                return None
            response.raise_for_status()
            return AuthorizedSubject.model_validate_json(response.content)
        except (httpx.HTTPError, ValidationError) as exc:
            raise UnexpectedProxyError("Failed to resolve verified proxy identity") from exc
