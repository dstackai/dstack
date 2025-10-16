from typing import List

from pydantic import ValidationError, parse_obj_as

from dstack._internal.core.models.users import GlobalRole, User, UserWithCreds
from dstack._internal.server.schemas.users import (
    CreateUserRequest,
    GetUserRequest,
    RefreshTokenRequest,
    UpdateUserRequest,
)
from dstack.api.server._group import APIClientGroup


class UsersAPIClient(APIClientGroup):
    def list(self) -> List[User]:
        resp = self._request("/api/users/list")
        return parse_obj_as(List[User.__response__], resp.json())

    def get_my_user(self) -> User:
        """
        Returns `User` with pre-0.19.33 servers, or `UserWithCreds` with newer servers.
        """

        resp = self._request("/api/users/get_my_user")
        try:
            return parse_obj_as(UserWithCreds.__response__, resp.json())
        except ValidationError as e:
            # Compatibility with pre-0.19.33 server
            if (
                len(e.errors()) == 1
                and e.errors()[0]["loc"] == ("__root__", "creds")
                and e.errors()[0]["type"] == "value_error.missing"
            ):
                return parse_obj_as(User.__response__, resp.json())
            else:
                raise

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
