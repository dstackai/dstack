import json

import pytest
from fastapi.testclient import TestClient

from dstack._internal.hub.main import app
from tests.hub.common import create_project, create_user

client = TestClient(app)


class TestListProject:
    @pytest.mark.asyncio
    async def test_global_admin_can_see_all_projects(self, test_db):
        user = await create_user(global_role="admin")
        project1 = await create_project(name="project1")
        project2 = await create_project(name="project2")
        response = client.post(
            "/api/projects/list", headers={"Authorization": f"Bearer {user.token}"}
        )
        assert response.status_code == 200


class TestCreateProject:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects/create")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_attempts_to_create_if_authenticated(self, test_db):
        user = await create_user(global_role="read")
        response = client.post(
            "/api/projects/create", headers={"Authorization": f"Bearer {user.token}"}
        )
        assert response.status_code not in [401, 403]


class TestDeleteProjects:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db):
        user = await create_user(global_role="read")
        project = await create_project()
        response = client.post(
            f"/api/projects/delete",
            headers={"Authorization": f"Bearer {user.token}"},
            json={"projects": [project.name]},
        )
        assert response.status_code == 403


class TestGetProjectInfo:
    @pytest.mark.asyncio
    async def test_returns_project_info(self, test_db):
        user = await create_user(global_role="admin")
        project = await create_project()
        response = client.post(
            f"/api/projects/{project.name}/info", headers={"Authorization": f"Bearer {user.token}"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "project_name": project.name,
            "backends": [],
            "members": [],
        }
