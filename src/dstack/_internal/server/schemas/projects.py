from typing import List

from pydantic import BaseModel

from dstack._internal.core.models.users import ProjectRole


class CreateProjectRequest(BaseModel):
    project_name: str


class DeleteProjectsRequest(BaseModel):
    projects_names: List[str]


class MemberSetting(BaseModel):
    username: str
    project_role: ProjectRole


class SetProjectMembersRequest(BaseModel):
    members: List[MemberSetting]
