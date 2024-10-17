import enum
from datetime import datetime
from typing import Optional

from pydantic import UUID4

from dstack._internal.core.models.common import CoreModel


class ProjectRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


class GlobalRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class UserPermissions(CoreModel):
    can_create_projects: bool


class User(CoreModel):
    id: UUID4
    username: str
    created_at: Optional[datetime] = None
    global_role: GlobalRole
    email: Optional[str]
    active: bool
    permissions: UserPermissions


class UserTokenCreds(CoreModel):
    token: str


class UserWithCreds(User):
    creds: UserTokenCreds
