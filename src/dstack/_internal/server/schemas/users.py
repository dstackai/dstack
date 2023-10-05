from pydantic import BaseModel

from dstack._internal.core.models.users import GlobalRole


class GetUserRequest(BaseModel):
    username: str


class CreateUserRequest(BaseModel):
    username: str
    global_role: GlobalRole


UpdateUserRequest = CreateUserRequest


class RefreshTokenRequest(BaseModel):
    username: str
