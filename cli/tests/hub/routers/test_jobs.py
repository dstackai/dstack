import pytest
from fastapi.testclient import TestClient

from dstack._internal.hub.main import app
from tests.hub.common import create_project, create_user

client = TestClient(app)


class TestGetJob:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db):
        project = await create_project()
        response = client.post(f"/api/project/{project.name}/jobs/get")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_attempts_to_get_if_authenticated(self, test_db):
        project = await create_project()
        user = await create_user(global_role="read")
        response = client.get(
            f"/api/project/{project.name}/jobs/get",
            headers={"Authorization": f"Bearer {user.token}"},
        )
        assert response.status_code not in [401, 403]
