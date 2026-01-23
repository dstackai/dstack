import json
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import parse_obj_as

from dstack._internal.core.models.projects import (
    Project,
    ProjectsInfoList,
    ProjectsInfoListOrProjectsList,
)
from dstack._internal.core.models.users import ProjectRole
from dstack._internal.server.schemas.projects import (
    AddProjectMemberRequest,
    CreateProjectRequest,
    DeleteProjectsRequest,
    MemberSetting,
    RemoveProjectMemberRequest,
    SetProjectMembersRequest,
)
from dstack.api.server._group import APIClientGroup


class ProjectsAPIClient(APIClientGroup):
    def list(
        self,
        include_not_joined: bool = True,
        return_total_count: Optional[bool] = None,
        name_pattern: Optional[str] = None,
        prev_created_at: Optional[datetime] = None,
        prev_id: Optional[UUID] = None,
        limit: Optional[int] = None,
        ascending: Optional[bool] = None,
    ) -> ProjectsInfoListOrProjectsList:
        # Passing only non-None fields for backward compatibility with 0.20 servers.
        body: dict[str, Any] = {
            "include_not_joined": include_not_joined,
        }
        if return_total_count is not None:
            body["return_total_count"] = return_total_count
        if name_pattern is not None:
            body["name_pattern"] = name_pattern
        if prev_created_at is not None:
            body["prev_created_at"] = prev_created_at.isoformat()
        if prev_id is not None:
            body["prev_id"] = str(prev_id)
        if limit is not None:
            body["limit"] = limit
        if ascending is not None:
            body["ascending"] = ascending
        resp = self._request("/api/projects/list", body=json.dumps(body))
        resp_json = resp.json()
        if isinstance(resp_json, list):
            return parse_obj_as(List[Project.__response__], resp_json)
        return parse_obj_as(ProjectsInfoList, resp_json)

    def create(self, project_name: str, is_public: bool = False) -> Project:
        body = CreateProjectRequest(project_name=project_name, is_public=is_public)
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

    def add_member(self, project_name: str, username: str, project_role: ProjectRole) -> Project:
        member_setting = MemberSetting(username=username, project_role=project_role)
        body = AddProjectMemberRequest(members=[member_setting])
        resp = self._request(f"/api/projects/{project_name}/add_members", body=body.json())
        return parse_obj_as(Project.__response__, resp.json())

    def add_members(self, project_name: str, members: List[MemberSetting]) -> Project:
        body = AddProjectMemberRequest(members=members)
        resp = self._request(f"/api/projects/{project_name}/add_members", body=body.json())
        return parse_obj_as(Project.__response__, resp.json())

    def remove_member(self, project_name: str, username: str) -> Project:
        body = RemoveProjectMemberRequest(usernames=[username])
        resp = self._request(f"/api/projects/{project_name}/remove_members", body=body.json())
        return parse_obj_as(Project.__response__, resp.json())

    def remove_members(self, project_name: str, usernames: List[str]) -> Project:
        body = RemoveProjectMemberRequest(usernames=usernames)
        resp = self._request(f"/api/projects/{project_name}/remove_members", body=body.json())
        return parse_obj_as(Project.__response__, resp.json())
