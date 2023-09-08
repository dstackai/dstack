import pytest
from fastapi.testclient import TestClient

from dstack._internal.server.main import app
from tests.server.common import create_user, get_auth_headers

client = TestClient(app)


class TestListUsers:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_users(self, test_db):
        user = await create_user()
        response = client.post("/api/users/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == [
            {
                "id": str(user.id),
                "username": user.name,
                "global_role": user.global_role,
            }
        ]


class TestGetMyUser:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/get_my_user")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_logged_in_user(self, test_db):
        user = await create_user()
        response = client.post("/api/users/get_my_user", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == {
            "id": str(user.id),
            "username": user.name,
            "global_role": user.global_role,
        }
