import json

import pytest
from fastapi.testclient import TestClient

from dstack.hub.main import app
from tests.hub.common import create_project, create_user

client = TestClient(app)


class TestListProject:
    @pytest.mark.asyncio
    async def test_global_admin_can_see_all_projects(self, test_db):
        user = await create_user(global_role="admin")
        project1 = await create_project(name="project1")
        project2 = await create_project(name="project2")
        response = client.get(
            "/api/projects/list", headers={"Authorization": f"Bearer {user.token}"}
        )
        assert response.status_code == 200


class TestCreateProject:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_attempts_to_create_if_authenticated(self, test_db):
        user = await create_user(global_role="read")
        response = client.post("/api/projects", headers={"Authorization": f"Bearer {user.token}"})
        assert response.status_code not in [401, 403]


class TestDeleteProjects:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db):
        user = await create_user(global_role="read")
        project = await create_project()
        response = client.request(
            "DELETE",
            f"/api/projects",
            headers={"Authorization": f"Bearer {user.token}"},
            json={"projects": [project.name]},
        )
        assert response.status_code == 403


class TestGetProjectInfo:
    @pytest.mark.asyncio
    async def test_successfull_response_format(self, test_db):
        user = await create_user(global_role="admin")
        project = await create_project()
        project_config = json.loads(project.config)
        response = client.get(
            f"/api/projects/{project.name}", headers={"Authorization": f"Bearer {user.token}"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "project_name": project.name,
            "backend": {
                "type": "aws",
                "region_name": project_config["region_name"],
                "region_name_title": project_config["region_name"],
                "s3_bucket_name": project_config["s3_bucket_name"],
                "ec2_subnet_id": project_config["ec2_subnet_id"],
            },
            "members": [],
        }


class TestGetProjectConfigInfo:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db):
        user = await create_user(global_role="read")
        project = await create_project()
        project_config = json.loads(project.config)
        response = client.get(
            f"/api/projects/{project.name}/config_info",
            headers={"Authorization": f"Bearer {user.token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_successfull_response_format(self, test_db):
        user = await create_user(global_role="admin")
        project = await create_project()
        project_config = json.loads(project.config)
        project_auth = json.loads(project.auth)
        response = client.get(
            f"/api/projects/{project.name}/config_info",
            headers={"Authorization": f"Bearer {user.token}"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "project_name": project.name,
            "backend": {
                "type": "aws",
                "access_key": project_auth["access_key"],
                "secret_key": project_auth["secret_key"],
                "region_name": project_config["region_name"],
                "region_name_title": project_config["region_name"],
                "s3_bucket_name": project_config["s3_bucket_name"],
                "ec2_subnet_id": project_config["ec2_subnet_id"],
            },
            "members": [],
        }
