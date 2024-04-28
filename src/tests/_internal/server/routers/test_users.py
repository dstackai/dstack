from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.main import app
from dstack._internal.server.models import UserModel
from dstack._internal.server.testing.common import create_user, get_auth_headers

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
                "email": None,
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
            "email": None,
        }


class TestGetUser:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/get_user")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_400_if_not_global_admin(self, test_db, session):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        other_user = await create_user(session=session, name="other_user", token="1234")
        response = client.post(
            "/api/users/get_user",
            headers=get_auth_headers(user.token),
            json={"username": other_user.name},
        )
        assert response.status_code == 400

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
            "email": None,
            "creds": {"token": "1234"},
        }


class TestCreateUser:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/create")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_creates_user(self, test_db, session: AsyncSession):
        user = await create_user(name="admin", session=session)
        with patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = client.post(
                "/api/users/create",
                headers=get_auth_headers(user.token),
                json={
                    "username": "test",
                    "global_role": GlobalRole.USER,
                    "email": "test@example.com",
                },
            )
        assert response.status_code == 200
        assert response.json() == {
            "id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
            "username": "test",
            "global_role": "user",
            "email": "test@example.com",
        }
        res = await session.execute(select(UserModel).where(UserModel.name == "test"))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_return_400_if_username_taken(self, test_db, session: AsyncSession):
        user = await create_user(name="admin", session=session)
        with patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = client.post(
                "/api/users/create",
                headers=get_auth_headers(user.token),
                json={
                    "username": "Test",
                    "global_role": GlobalRole.USER,
                },
            )
        assert response.status_code == 200
        assert response.json() == {
            "id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
            "username": "Test",
            "global_role": "user",
            "email": None,
        }
        # Username uniqueness check should be case insensitive
        for username in ["test", "Test", "TesT"]:
            with patch("uuid.uuid4") as uuid_mock:
                uuid_mock.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
                response = client.post(
                    "/api/users/create",
                    headers=get_auth_headers(user.token),
                    json={
                        "username": username,
                        "global_role": GlobalRole.USER,
                    },
                )
            assert response.status_code == 400
        res = await session.execute(
            select(UserModel).where(UserModel.name.in_(["test", "Test", "TesT"]))
        )
        assert len(res.scalars().all()) == 1


class TestDeleteUsers:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/delete")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_deletes_users(self, test_db, session: AsyncSession):
        admin = await create_user(name="admin", session=session)
        user = await create_user(name="test", session=session)
        response = client.post(
            "/api/users/delete",
            headers=get_auth_headers(admin.token),
            json={"users": [user.name]},
        )
        assert response.status_code == 200
        res = await session.execute(select(UserModel).where(UserModel.name == user.name))
        assert len(res.scalars().all()) == 0
