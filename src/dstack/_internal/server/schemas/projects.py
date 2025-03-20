from typing import Annotated, List

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import ProjectRole


class CreateProjectRequest(CoreModel):
    project_name: str


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
