from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.projects import Project
from dstack._internal.server.schemas.projects import (
    CreateProjectRequest,
    DeleteProjectsRequest,
    MemberSetting,
    SetProjectMembersRequest,
)
from dstack.api.server._group import APIClientGroup


class ProjectsAPIClient(APIClientGroup):
    def list(self) -> List[Project]:
        resp = self._request("/api/projects/list")
        return parse_obj_as(List[Project.__response__], resp.json())

    def create(self, project_name: str) -> Project:
        body = CreateProjectRequest(project_name=project_name)
        resp = self._request("/api/projects/create", body=body.json())
        return parse_obj_as(Project.__response__, resp.json())

    def delete(self, projects_names: List[str]):
        body = DeleteProjectsRequest(projects_names=projects_names)
        self._request("/api/projects/delete", body=body.json())

    def get(self, project_name: str) -> Project:
        resp = self._request(f"/api/projects/{project_name}/get")
        return parse_obj_as(Project.__response__, resp.json())

    def set_members(self, project_name: str, members: List[MemberSetting]) -> Project:
        body = SetProjectMembersRequest(members=members)
        resp = self._request(f"/api/projects/{project_name}/set_members", body=body.json())
        return parse_obj_as(Project.__response__, resp.json())
