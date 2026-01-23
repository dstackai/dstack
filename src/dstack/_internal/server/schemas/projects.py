from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import ProjectRole


class ListProjectsRequest(CoreModel):
    include_not_joined: Annotated[
        bool, Field(description="Include public projects where user is not a member.")
    ] = True
    return_total_count: Annotated[
        bool, Field(description="Return `total_count` with the total number of projects.")
    ] = False
    name_pattern: Annotated[
        Optional[str],
        Field(
            description="Include only projects with the name containing `name_pattern`.",
            regex="^[a-zA-Z0-9-_]*$",
        ),
    ] = None
    prev_created_at: Annotated[
        Optional[datetime],
        Field(
            description="Paginate projects by specifying `created_at` of the last (first) project in previous batch for descending (ascending)."
        ),
    ] = None
    prev_id: Annotated[
        Optional[UUID],
        Field(
            description=(
                "Paginate projects by specifying `id` of the last (first) project in previous batch for descending (ascending)."
                " Must be used together with `prev_created_at`."
            )
        ),
    ] = None
    limit: Annotated[
        int, Field(ge=0, le=2000, description="Limit number of projects returned.")
    ] = 2000
    ascending: Annotated[
        bool,
        Field(
            description="Return projects sorted by `created_at` in ascending order. Defaults to descending."
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
