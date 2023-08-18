import json

import pytest
from fastapi.testclient import TestClient

from dstack._internal.hub.main import app
from dstack._internal.hub.repository.projects import ProjectManager
from tests.hub.common import create_backend, create_project, create_user

client = TestClient(app)


class TestListBackend:
    @pytest.mark.asyncio
    async def test_returns_backends(self, test_db):
        user = await create_user()
        project = await create_project()
        backend = await create_backend(project_name=project.name)
        response = client.post(
            f"/api/project/{project.name}/backends/list",
            headers={"Authorization": f"Bearer {user.token}"},
        )
        assert response.status_code == 200
        body = response.json()
        config = json.loads(backend.config)
        assert body == [
            {
                "name": backend.name,
                "config": {
                    "type": backend.type,
                    "regions": config["regions"],
                    "s3_bucket_name": config["s3_bucket_name"],
                    "ec2_subnet_id": config["ec2_subnet_id"],
                },
            }
        ]


class TestGetBackendInfo:
    @pytest.mark.asyncio
    async def test_returns_backend_info(self, test_db):
        user = await create_user()
        project = await create_project()
        backend = await create_backend(project_name=project.name)
        response = client.post(
            f"/api/project/{project.name}/backends/{backend.name}/config_info",
            headers={"Authorization": f"Bearer {user.token}"},
        )
        assert response.status_code == 200
        body = response.json()
        config = json.loads(backend.config)
        auth = json.loads(backend.auth)
        assert body == {
            "name": backend.name,
            "config": {
                "type": backend.type,
                "credentials": {
                    "type": "access_key",
                    "access_key": auth["access_key"],
                    "secret_key": auth["secret_key"],
                },
                "regions": config["regions"],
                "s3_bucket_name": config["s3_bucket_name"],
                "ec2_subnet_id": config["ec2_subnet_id"],
            },
        }


class TestCreateBackend:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db):
        project = await create_project()
        response = client.post(f"/api/project/{project.name}/backends/create")
        assert response.status_code in [401, 403]


class TestDeleteBackends:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db):
        user = await create_user(global_role="read")
        project = await create_project()
        backend = await create_backend(project_name=project.name)
        response = client.post(
            f"/api/project/{project.name}/backends/delete",
            headers={"Authorization": f"Bearer {user.token}"},
            json={"backends": [backend.name]},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_deletes_backends(self, test_db):
        user = await create_user(global_role="admin")
        project = await create_project()
        backend = await create_backend(project_name=project.name)
        response = client.post(
            f"/api/project/{project.name}/backends/delete",
            headers={"Authorization": f"Bearer {user.token}"},
            json={"backends": [backend.name]},
        )
        assert response.status_code == 200
        backend = await ProjectManager.get_backend(project=project, backend_name=backend.name)
        assert backend is None
