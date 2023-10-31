from typing import List

from pydantic import UUID4, BaseModel

from dstack._internal.core.models.backends import BackendInfo
from dstack._internal.core.models.users import ProjectRole, User


class Member(BaseModel):
    user: User
    project_role: ProjectRole


class Project(BaseModel):
    project_id: UUID4
    project_name: str
    owner: User
    backends: List[BackendInfo]
    members: List[Member]
