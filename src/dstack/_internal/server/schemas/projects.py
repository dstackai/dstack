from typing import Annotated, List

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import ProjectRole


class CreateProjectRequest(CoreModel):
    project_name: str
    is_public: bool = False


class UpdateProjectRequest(CoreModel):
    is_public: bool


class DeleteProjectsRequest(CoreModel):
    projects_names: List[str]


class MemberSetting(CoreModel):
    username: Annotated[
        str,
        Field(description="The username or email of the user"),
    ]
    project_role: ProjectRole


class SetProjectMembersRequest(CoreModel):
    members: List[MemberSetting]


class AddProjectMemberRequest(CoreModel):
    members: List[MemberSetting]


class RemoveProjectMemberRequest(CoreModel):
    usernames: List[str]
