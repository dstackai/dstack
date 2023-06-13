import pytest
from fastapi.testclient import TestClient

from dstack._internal.hub.main import app
from dstack._internal.hub.repository.users import UserManager
from tests.hub.common import create_project, create_user

client = TestClient(app)


class TestListUsers:
    def test_returns_40x_if_not_authenticated(self):
        response = client.get("/api/users/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_global_admins_see_all_users(self, test_db):
        user1 = await create_user(name="user1", global_role="admin", token="user1")
        user2 = await create_user(name="user2", global_role="read", token="user2")
        response = client.get(
            "/api/users/list", headers={"Authorization": f"Bearer {user1.token}"}
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "user_name": user1.name,
                "global_role": user1.global_role,
            },
            {
                "user_name": user2.name,
                "global_role": user2.global_role,
            },
        ]

    @pytest.mark.asyncio
    async def test_non_global_admins_see_only_themselves(self, test_db):
        user1 = await create_user(name="user1", global_role="admin", token="user1")
        user2 = await create_user(name="user2", global_role="read", token="user2")
        response = client.get(
            "/api/users/list", headers={"Authorization": f"Bearer {user2.token}"}
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "user_name": user2.name,
                "global_role": user2.global_role,
            },
        ]


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_global_admin_can_create_users(self, test_db):
        user1 = await create_user(name="user1", global_role="admin", token="user1")
        response = client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {user1.token}"},
            json={
                "user_name": "user2",
                "global_role": "admin",
            },
        )
        assert response.status_code == 200
        user2 = await UserManager.get_user_by_name("user2")
        assert user2 is not None

    @pytest.mark.asyncio
    async def test_non_global_admin_cannot_create_users(self, test_db):
        user1 = await create_user(name="user1", global_role="read", token="user1")
        response = client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {user1.token}"},
            json={
                "user_name": "user2",
                "global_role": "admin",
            },
        )
        assert response.status_code == 403
        user2 = await UserManager.get_user_by_name("user2")
        assert user2 is None
