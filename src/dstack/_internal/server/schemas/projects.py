from typing import Annotated, List

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import ProjectRole


class CreateProjectRequest(CoreModel):
    project_name: str
    is_public: bool = False


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
    # Always accept a list of members for cleaner API design
    members: List[MemberSetting]


class RemoveProjectMemberRequest(CoreModel):
    # Always accept a list of usernames for cleaner API design
    usernames: List[str]
