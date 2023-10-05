import enum

from pydantic import UUID4, BaseModel


class ProjectRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class GlobalRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(BaseModel):
    id: UUID4
    username: str
    global_role: GlobalRole


class UserTokenCreds(BaseModel):
    token: str


class UserWithCreds(User):
    creds: UserTokenCreds
