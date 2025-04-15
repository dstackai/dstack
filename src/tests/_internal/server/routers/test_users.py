from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.models import UserModel
from dstack._internal.server.testing.common import create_user, get_auth_headers


class TestListUsers:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/users/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_users(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = await client.post("/api/users/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == [
            {
                "id": str(user.id),
                "username": user.name,
                "created_at": "2023-01-02T03:04:00+00:00",
                "global_role": user.global_role,
                "email": None,
                "active": True,
                "permissions": {
                    "can_create_projects": True,
                },
            }
        ]


class TestGetMyUser:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/users/get_my_user")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_deactivated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, active=False)
        response = await client.post(
            "/api/users/get_my_user", headers=get_auth_headers(user.token)
        )
        assert response.status_code in [401, 403]
        user.active = True
        await session.commit()
        response = await client.post(
            "/api/users/get_my_user", headers=get_auth_headers(user.token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_logged_in_user(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = await client.post(
            "/api/users/get_my_user", headers=get_auth_headers(user.token)
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": str(user.id),
            "username": user.name,
            "created_at": "2023-01-02T03:04:00+00:00",
            "global_role": user.global_role,
            "email": None,
            "active": True,
            "permissions": {
                "can_create_projects": True,
            },
        }


class TestGetUser:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/users/get_user")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_not_global_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        other_user = await create_user(session=session, name="other_user", token="1234")
        response = await client.post(
            "/api/users/get_user",
            headers=get_auth_headers(user.token),
            json={"username": other_user.name},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_logged_in_user(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.ADMIN)
        other_user = await create_user(
            session=session,
            name="other_user",
            token="1234",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = await client.post(
            "/api/users/get_user",
            headers=get_auth_headers(user.token),
            json={"username": other_user.name},
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": str(other_user.id),
            "username": other_user.name,
            "created_at": "2023-01-02T03:04:00+00:00",
            "global_role": other_user.global_role,
            "email": None,
            "creds": {"token": "1234"},
            "active": True,
            "permissions": {
                "can_create_projects": True,
            },
        }


class TestCreateUser:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/users/create")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_user(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(name="admin", session=session)
        with patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = await client.post(
                "/api/users/create",
                headers=get_auth_headers(user.token),
                json={
                    "username": "test",
                    "global_role": GlobalRole.USER,
                    "email": "test@example.com",
                    "active": True,
                },
            )
        assert response.status_code == 200
        assert response.json() == {
            "id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
            "username": "test",
            "created_at": "2023-01-02T03:04:00+00:00",
            "global_role": "user",
            "email": "test@example.com",
            "active": True,
            "permissions": {
                "can_create_projects": True,
            },
        }
        res = await session.execute(select(UserModel).where(UserModel.name == "test"))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_return_400_if_username_taken(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(
            name="admin",
            session=session,
        )
        with patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = await client.post(
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
            "created_at": "2023-01-02T03:04:00+00:00",
            "global_role": "user",
            "email": None,
            "active": True,
            "permissions": {
                "can_create_projects": True,
            },
        }
        # Username uniqueness check should be case insensitive
        for username in ["test", "Test", "TesT"]:
            with patch("uuid.uuid4") as uuid_mock:
                uuid_mock.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
                response = await client.post(
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_returns_400_if_username_invalid(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
    ):
        user = await create_user(
            name="admin",
            session=session,
        )
        response = await client.post(
            "/api/users/create",
            headers=get_auth_headers(user.token),
            json={
                "username": "Invalid#$username",
                "global_role": GlobalRole.USER,
            },
        )
        assert response.status_code == 400


class TestDeleteUsers:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/users/delete")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_users(self, test_db, session: AsyncSession, client: AsyncClient):
        admin = await create_user(name="admin", session=session)
        user = await create_user(name="test", session=session)
        response = await client.post(
            "/api/users/delete",
            headers=get_auth_headers(admin.token),
            json={"users": [user.name]},
        )
        assert response.status_code == 200
        res = await session.execute(select(UserModel).where(UserModel.name == user.name))
        assert len(res.scalars().all()) == 0


class TestRefreshToken:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/users/refresh_token")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_refreshes_token(self, test_db, session: AsyncSession, client: AsyncClient):
        user1 = await create_user(name="user1", session=session)
        old_token = user1.token
        response = await client.post(
            "/api/users/refresh_token",
            headers=get_auth_headers(user1.token),
            json={"username": user1.name},
        )
        assert response.status_code == 200
        assert response.json()["creds"]["token"] != old_token
        await session.refresh(user1)
        assert user1.token != old_token

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_non_admin_refreshes_for_other_user(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user1 = await create_user(name="user1", session=session, global_role=GlobalRole.USER)
        user2 = await create_user(name="user2", session=session)
        response = await client.post(
            "/api/users/refresh_token",
            headers=get_auth_headers(user1.token),
            json={"username": user2.name},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_global_admin_refreshes_token(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user1 = await create_user(name="user1", session=session, global_role=GlobalRole.ADMIN)
        user2 = await create_user(name="user2", session=session)
        old_token = user2.token
        response = await client.post(
            "/api/users/refresh_token",
            headers=get_auth_headers(user1.token),
            json={"username": user2.name},
        )
        assert response.status_code == 200
        assert response.json()["creds"]["token"] != old_token
        await session.refresh(user2)
        assert user2.token != old_token
