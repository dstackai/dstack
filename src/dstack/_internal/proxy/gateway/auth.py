import uuid
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx2 as httpx
from aiocache import cached
from fastapi import status
from pydantic import BaseModel

from dstack._internal.core.models.users import GlobalRole
from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider, ProxyCaller
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError

_AUTH_CACHE_TTL_SECONDS = 60
"""Seconds to cache allowed or denied access for each project/token pair,
and the answer that the project does not exist."""
_USER_ID_CACHE_TTL_SECONDS = 3600
"""Seconds to cache the user ID of each token. Access is still rechecked
every `_AUTH_CACHE_TTL_SECONDS`, so a revoked token stops working within that time."""


@dataclass(frozen=True)
class _ProjectAccess:
    """The server's answer on whether a token can access a project."""

    project_id: Optional[uuid.UUID]
    """`None` if access is denied or the project does not exist."""
    member_ids: frozenset[uuid.UUID] = frozenset()
    """The project's members. The server also allows global admins,
    and any user if the project is public."""
    project_exists: bool = True
    """`False` if the server has no project with this name."""


class GatewayProxyAuthProvider(BaseProxyAuthProvider):
    def __init__(self, server_client: httpx.AsyncClient) -> None:
        self._server_client = server_client

    async def is_project_member(self, project_name: str, token: str) -> bool:
        access = await self._get_project_access(project_name, token)
        return access.project_id is not None

    async def get_caller(self, project_name: str, token: str) -> Optional[ProxyCaller]:
        access = await self._get_project_access(project_name, token)
        if not access.project_exists:
            raise ProxyError(f"Project {project_name} not found", status.HTTP_404_NOT_FOUND)
        if access.project_id is None:
            return None
        user_id = await self._get_user_id(token)
        if user_id is None:
            return None
        if user_id not in access.member_ids and not await self._is_global_admin(token):
            return None
        return ProxyCaller(project_id=access.project_id, user_id=user_id)

    @cached(ttl=_AUTH_CACHE_TTL_SECONDS, noself=True)
    async def _get_project_access(self, project_name: str, token: str) -> _ProjectAccess:
        # The project name comes from the URL of the user's request, so it is quoted.
        resp = await self._request(
            f"/api/projects/{quote(project_name, safe='')}/get", token, allow_not_found=True
        )
        if resp is None:
            return _ProjectAccess(project_id=None)
        if resp.status_code == httpx.codes.NOT_FOUND:
            return _ProjectAccess(project_id=None, project_exists=False)
        project = _Project.model_validate_json(resp.content)
        return _ProjectAccess(
            project_id=project.project_id,
            member_ids=frozenset(member.user.id for member in project.members),
        )

    @cached(ttl=_USER_ID_CACHE_TTL_SECONDS, noself=True, skip_cache_func=lambda r: r is None)
    async def _get_user_id(self, token: str) -> Optional[uuid.UUID]:
        user = await self._get_user(token)
        return user.id if user is not None else None

    @cached(ttl=_AUTH_CACHE_TTL_SECONDS, noself=True)
    async def _is_global_admin(self, token: str) -> bool:
        user = await self._get_user(token)
        return user is not None and user.global_role == GlobalRole.ADMIN

    async def _get_user(self, token: str) -> Optional["_User"]:
        resp = await self._request("/api/users/get_my_user", token)
        if resp is None:
            return None
        return _User.model_validate_json(resp.content)

    async def _request(
        self, path: str, token: str, allow_not_found: bool = False
    ) -> Optional[httpx.Response]:
        """
        Returns `None` if the server denies access with the token.
        With `allow_not_found`, returns the server's 404 response instead of raising.
        """
        try:
            resp = await self._server_client.post(
                path, headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == httpx.codes.FORBIDDEN:
                return None
            if not (allow_not_found and resp.status_code == httpx.codes.NOT_FOUND):
                resp.raise_for_status()
        except httpx.HTTPError as e:
            raise UnexpectedProxyError(
                f"Failed requesting dstack-server to check access: {e!r}"
            ) from e
        return resp


# Only the fields that access checks need are parsed from the server's responses,
# so that changes to the other fields cannot break gateways that are not updated yet.


class _MemberUser(BaseModel):
    id: uuid.UUID


class _Member(BaseModel):
    user: _MemberUser


class _Project(BaseModel):
    project_id: uuid.UUID
    members: list[_Member]


class _User(BaseModel):
    id: uuid.UUID
    global_role: str
