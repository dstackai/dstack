from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic_core import to_json

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.users import (
    GlobalRole,
    User,
    UsersInfoList,
    UsersInfoListOrUsersList,
    UserWithCreds,
)
from dstack._internal.server.schemas.users import (
    CreateUserRequest,
    GetUserRequest,
    RefreshTokenRequest,
    UpdateUserRequest,
)
from dstack.api.server._group import APIClientGroup


class UsersAPIClient(APIClientGroup):
    def list(
        self,
        return_total_count: Optional[bool] = None,
        name_pattern: Optional[str] = None,
        prev_created_at: Optional[datetime] = None,
        prev_id: Optional[UUID] = None,
        limit: Optional[int] = None,
        ascending: Optional[bool] = None,
    ) -> UsersInfoListOrUsersList:
        # Passing only non-None fields for backward compatibility with 0.20 servers.
        body: dict[str, Any] = {}
        if return_total_count is not None:
            body["return_total_count"] = return_total_count
        if name_pattern is not None:
            body["name_pattern"] = name_pattern
        if prev_created_at is not None:
            body["prev_created_at"] = prev_created_at
        if prev_id is not None:
            body["prev_id"] = prev_id
        if limit is not None:
            body["limit"] = limit
        if ascending is not None:
            body["ascending"] = ascending
        if body:
            resp = self._request("/api/users/list", body=to_json(body))
        else:
            resp = self._request("/api/users/list")
        resp_json = resp.json()
        if isinstance(resp_json, list):
            return validate_extra_ignore(List[User], resp_json)
        return validate_extra_ignore(UsersInfoList, resp_json)

    def get_my_user(self) -> UserWithCreds:
        resp = self._request("/api/users/get_my_user")
        return validate_extra_ignore(UserWithCreds, resp.json())

    def get_user(self, username: str) -> User:
        body = GetUserRequest(username=username)
        resp = self._request("/api/users/get_user", body=body.model_dump_json())
        return validate_extra_ignore(User, resp.json())

    def create(self, username: str, global_role: GlobalRole) -> User:
        body = CreateUserRequest(username=username, global_role=global_role, email=None)
        resp = self._request("/api/users/create", body=body.model_dump_json())
        return validate_extra_ignore(User, resp.json())

    def update(self, username: str, global_role: GlobalRole) -> User:
        body = UpdateUserRequest(username=username, global_role=global_role, email=None)
        resp = self._request("/api/users/update", body=body.model_dump_json())
        return validate_extra_ignore(User, resp.json())

    def refresh_token(self, username: str) -> UserWithCreds:
        body = RefreshTokenRequest(username=username)
        resp = self._request("/api/users/refresh_token", body=body.model_dump_json())
        return validate_extra_ignore(UserWithCreds, resp.json())
