import enum
from typing import Optional

from pydantic import UUID4

from dstack._internal.core.models.common import CoreModel


class ProjectRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class GlobalRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(CoreModel):
    id: UUID4
    username: str
    global_role: GlobalRole
    email: Optional[str]


class UserTokenCreds(CoreModel):
    token: str


class UserWithCreds(User):
    creds: UserTokenCreds
