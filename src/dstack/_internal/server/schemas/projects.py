from typing import List

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import ProjectRole


class CreateProjectRequest(CoreModel):
    project_name: str


class DeleteProjectsRequest(CoreModel):
    projects_names: List[str]


class MemberSetting(CoreModel):
    username: str
    project_role: ProjectRole


class SetProjectMembersRequest(CoreModel):
    members: List[MemberSetting]
