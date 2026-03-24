import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.models import UserPublicKeyModel
from dstack._internal.server.testing.common import (
    create_user,
    create_user_public_key,
    get_auth_headers,
)
from dstack._internal.server.testing.matchers import SomeUUID4Str


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db")
class TestListUserPublicKeys:
    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/users/public_keys/list")
        assert response.status_code in [401, 403]

    async def test_lists_own_public_keys(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session)
        key = await create_user_public_key(
            session=session,
            user=user,
            name="my-key",
            type="ssh-ed25519",
            fingerprint="SHA256:testfingerprint",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = await client.post(
            "/api/users/public_keys/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(key.id),
                "added_at": "2023-01-02T03:04:00+00:00",
                "name": "my-key",
                "type": "ssh-ed25519",
                "fingerprint": "SHA256:testfingerprint",
            }
        ]

    async def test_does_not_list_other_users_keys(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        other_user = await create_user(session=session, name="other_user")
        await create_user_public_key(session=session, user=other_user)
        response = await client.post(
            "/api/users/public_keys/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_keys_in_reverse_chronological_order(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        key1 = await create_user_public_key(
            session=session,
            user=user,
            name="older-key",
            fingerprint="SHA256:fingerprint1",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        key2 = await create_user_public_key(
            session=session,
            user=user,
            name="newer-key",
            fingerprint="SHA256:fingerprint2",
            created_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
        )
        response = await client.post(
            "/api/users/public_keys/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(key2.id)
        assert data[1]["id"] == str(key1.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db")
class TestAddUserPublicKey:
    PUBLIC_KEY_NO_COMMENT = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA"
    PUBLIC_KEY = f"{PUBLIC_KEY_NO_COMMENT} test@example.com"

    @pytest.fixture
    def validate_openssh_public_key_mock(self, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
        mock = AsyncMock()
        monkeypatch.setattr(
            "dstack._internal.server.services.public_keys.validate_openssh_public_key", mock
        )
        return mock

    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/users/public_keys/add",
            json={"key": self.PUBLIC_KEY},
        )
        assert response.status_code in [401, 403]

    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_adds_valid_public_key(
        self,
        session: AsyncSession,
        client: AsyncClient,
        validate_openssh_public_key_mock: AsyncMock,
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/users/public_keys/add",
            headers=get_auth_headers(user.token),
            json={"key": self.PUBLIC_KEY},
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "type": "ssh-ed25519",
            "name": "test@example.com",
            "fingerprint": "SHA256:uALbfMqe7g4MMaRS5NMJen38dAEHwtxzR0iX0Ymuc80",
            "added_at": "2023-01-02T03:04:00+00:00",
        }
        validate_openssh_public_key_mock.assert_awaited_once_with(self.PUBLIC_KEY)

    @pytest.mark.usefixtures("validate_openssh_public_key_mock")
    async def test_adds_key_with_custom_name(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session)
        response = await client.post(
            "/api/users/public_keys/add",
            headers=get_auth_headers(user.token),
            json={"key": self.PUBLIC_KEY, "name": "my-laptop"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "my-laptop"

    @pytest.mark.usefixtures("validate_openssh_public_key_mock")
    async def test_uses_md5_as_name_when_no_comment_and_no_name(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/users/public_keys/add",
            headers=get_auth_headers(user.token),
            json={"key": self.PUBLIC_KEY_NO_COMMENT},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "744e414c6ac55e3f15c1dd48229cbe74"

    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("sha-rsa-invalid", id="only-one-field"),
            pytest.param("ssh-rsa AAAAB3NzaC1kc3M=", id="dsa-declared-as-rsa"),
        ],
    )
    async def test_returns_400_for_invalid_key(
        self, session: AsyncSession, client: AsyncClient, key: str
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/users/public_keys/add",
            headers=get_auth_headers(user.token),
            json={"key": key},
        )
        assert response.status_code == 400
        assert "Invalid public key" in response.json()["detail"][0]["msg"]

    async def test_returns_400_for_unsupported_key(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/users/public_keys/add",
            headers=get_auth_headers(user.token),
            json={"key": "ssh-dss AAAAB3NzaC1kc3M="},
        )
        assert response.status_code == 400
        assert response.json()["detail"][0]["msg"] == "Unsupported key type: ssh-dss"

    @pytest.mark.usefixtures("validate_openssh_public_key_mock")
    async def test_returns_400_resource_exists_for_duplicate_key(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/users/public_keys/add",
            headers=get_auth_headers(user.token),
            json={"key": self.PUBLIC_KEY},
        )
        assert response.status_code == 200
        response = await client.post(
            "/api/users/public_keys/add",
            headers=get_auth_headers(user.token),
            # The same key, the comment does not matter
            json={"key": self.PUBLIC_KEY_NO_COMMENT},
        )
        assert response.status_code == 400
        assert response.json()["detail"][0]["code"] == "resource_exists"


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db")
class TestDeleteUserPublicKeys:
    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/users/public_keys/delete",
            json={"ids": [str(uuid.uuid4())]},
        )
        assert response.status_code in [401, 403]

    async def test_deletes_public_key(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session)
        key = await create_user_public_key(session=session, user=user)
        other_key = await create_user_public_key(
            session=session, user=user, fingerprint="SHA256:other"
        )
        response = await client.post(
            "/api/users/public_keys/delete",
            headers=get_auth_headers(user.token),
            json={"ids": [str(key.id)]},
        )
        assert response.status_code == 200
        res = await session.execute(
            select(UserPublicKeyModel).where(UserPublicKeyModel.user_id == user.id)
        )
        assert res.scalars().all() == [other_key]

    async def test_silently_ignores_nonexistent_ids(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/users/public_keys/delete",
            headers=get_auth_headers(user.token),
            json={"ids": [str(uuid.uuid4())]},
        )
        assert response.status_code == 200

    async def test_does_not_delete_other_users_keys(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        other_user = await create_user(session=session, name="other_user")
        other_user_key = await create_user_public_key(session=session, user=other_user)
        response = await client.post(
            "/api/users/public_keys/delete",
            headers=get_auth_headers(user.token),
            json={"ids": [str(other_user_key.id)]},
        )
        assert response.status_code == 200
        res = await session.execute(
            select(UserPublicKeyModel).where(UserPublicKeyModel.user_id == other_user.id)
        )
        assert res.scalars().all() == [other_user_key]
