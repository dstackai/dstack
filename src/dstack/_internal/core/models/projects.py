from datetime import datetime
from typing import List, Optional

from pydantic import UUID4

from dstack._internal.core.backends.models import BackendInfo
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import ProjectRole, User


class MemberPermissions(CoreModel):
    can_manage_ssh_fleets: bool


class Member(CoreModel):
    user: User
    project_role: ProjectRole
    permissions: MemberPermissions


class Project(CoreModel):
    project_id: UUID4
    project_name: str
    owner: User
    created_at: Optional[datetime] = None
    backends: List[BackendInfo]
    members: List[Member]
    is_public: bool = False
