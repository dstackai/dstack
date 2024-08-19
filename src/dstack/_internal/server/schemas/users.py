from typing import List, Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import GlobalRole


class GetUserRequest(CoreModel):
    username: str


class CreateUserRequest(CoreModel):
    username: str
    global_role: GlobalRole
    email: Optional[str]
    active: bool = True


UpdateUserRequest = CreateUserRequest


class RefreshTokenRequest(CoreModel):
    username: str


class DeleteUsersRequest(CoreModel):
    users: List[str]
