import json
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import parse_obj_as
from pydantic.json import pydantic_encoder

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
        prev_created_at: Optional[datetime] = None,
        prev_id: Optional[UUID] = None,
        limit: Optional[int] = None,
        ascending: Optional[bool] = None,
    ) -> UsersInfoListOrUsersList:
        # Passing only non-None fields for backward compatibility with 0.20 servers.
        body: dict[str, Any] = {}
        if return_total_count is not None:
            body["return_total_count"] = return_total_count
        if prev_created_at is not None:
            body["prev_created_at"] = prev_created_at
        if prev_id is not None:
            body["prev_id"] = prev_id
        if limit is not None:
            body["limit"] = limit
        if ascending is not None:
            body["ascending"] = ascending
        if body:
            resp = self._request(
                "/api/users/list", body=json.dumps(body, default=pydantic_encoder)
            )
        else:
            resp = self._request("/api/users/list")
        resp_json = resp.json()
        if isinstance(resp_json, list):
            return parse_obj_as(List[User.__response__], resp_json)
        return parse_obj_as(UsersInfoList, resp_json)

    def get_my_user(self) -> UserWithCreds:
        resp = self._request("/api/users/get_my_user")
        return parse_obj_as(UserWithCreds.__response__, resp.json())

    def get_user(self, username: str) -> User:
        body = GetUserRequest(username=username)
        resp = self._request("/api/users/get_user", body=body.json())
        return parse_obj_as(User.__response__, resp.json())

    def create(self, username: str, global_role: GlobalRole) -> User:
        body = CreateUserRequest(username=username, global_role=global_role, email=None)
        resp = self._request("/api/users/create", body=body.json())
        return parse_obj_as(User.__response__, resp.json())

    def update(self, username: str, global_role: GlobalRole) -> User:
        body = UpdateUserRequest(username=username, global_role=global_role, email=None)
        resp = self._request("/api/users/update", body=body.json())
        return parse_obj_as(User.__response__, resp.json())

    def refresh_token(self, username: str) -> UserWithCreds:
        body = RefreshTokenRequest(username=username)
        resp = self._request("/api/users/refresh_token", body=body.json())
        return parse_obj_as(UserWithCreds.__response__, resp.json())
