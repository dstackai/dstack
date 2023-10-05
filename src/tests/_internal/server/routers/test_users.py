import pytest
from fastapi.testclient import TestClient

from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.main import app
from tests._internal.server.common import create_user, get_auth_headers

client = TestClient(app)


class TestListUsers:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_users(self, test_db, session):
        user = await create_user(session=session)
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
    async def test_returns_logged_in_user(self, test_db, session):
        user = await create_user(session=session)
        response = client.post("/api/users/get_my_user", headers=get_auth_headers(user.token))
        assert response.status_code == 200
        assert response.json() == {
            "id": str(user.id),
            "username": user.name,
            "global_role": user.global_role,
        }


class TestGetUser:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/get_user")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_404_if_not_global_admin(self, test_db, session):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        other_user = await create_user(session=session, name="other_user", token="1234")
        response = client.post(
            "/api/users/get_user",
            headers=get_auth_headers(user.token),
            json={"username": other_user.name},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_logged_in_user(self, test_db, session):
        user = await create_user(session=session, global_role=GlobalRole.ADMIN)
        other_user = await create_user(session=session, name="other_user", token="1234")
        response = client.post(
            "/api/users/get_user",
            headers=get_auth_headers(user.token),
            json={"username": other_user.name},
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": str(other_user.id),
            "username": other_user.name,
            "global_role": other_user.global_role,
            "creds": {"token": "1234"},
        }
