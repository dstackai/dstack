from typing import Annotated, List

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import ProjectRole


class ListProjectsRequest(CoreModel):
    include_not_joined: Annotated[
        bool, Field(description="Include public projects where user is not a member")
    ] = True
    only_no_fleets: Annotated[
        bool,
        Field(
            description=(
                "If true, returns only projects where the user is a member and that have no active fleets. "
                "Active fleets are those with `deleted == False`. "
                "Projects with deleted fleets (but no active fleets) are included."
            )
        ),
    ] = False


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
