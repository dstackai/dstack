import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import SecretModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_project,
    create_secret,
    create_user,
    get_auth_headers,
)


class TestListSecrets:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_lists_secrets(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        secret1 = await create_secret(
            session=session, project=project, name="secret1", value="123456"
        )
        secret2 = await create_secret(
            session=session, project=project, name="secret2", value="123456"
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(secret2.id),
                "name": "secret2",
                "value": None,
            },
            {
                "id": str(secret1.id),
                "name": "secret1",
                "value": None,
            },
        ]


class TestGetSecret:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/get",
            headers=get_auth_headers(user.token),
            json={"name": "my_secret"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_secret_with_value(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        secret = await create_secret(
            session=session, project=project, name="secret1", value="123456"
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/get",
            headers=get_auth_headers(user.token),
            json={"name": "secret1"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": str(secret.id),
            "name": "secret1",
            "value": "123456",
        }


class TestCreateOrUpdateSecret:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/create_or_update",
            headers=get_auth_headers(user.token),
            json={"name": "my_secret"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_secret(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/create_or_update",
            headers=get_auth_headers(user.token),
            json={"name": "secret1", "value": "123456"},
        )
        assert response.status_code == 200
        res = await session.execute(select(SecretModel))
        secret_model = res.scalar()
        assert secret_model is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_updates_secret(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        secret = await create_secret(
            session=session, project=project, name="secret1", value="old_value"
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/create_or_update",
            headers=get_auth_headers(user.token),
            json={"name": "secret1", "value": "new_value"},
        )
        assert response.status_code == 200
        await session.refresh(secret)
        assert secret.value.get_plaintext_or_error() == "new_value"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "name, value",
        [
            ("too_long_secret_value", "a" * 3001),
            ("", "empty_name"),
            ("@7&.", "wierd_name_chars"),
        ],
    )
    async def test_rejects_bad_names_values(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        name: str,
        value,
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/create_or_update",
            headers=get_auth_headers(user.token),
            json={"name": name, "value": value},
        )
        assert response.status_code == 400
        res = await session.execute(select(SecretModel))
        secret_model = res.scalar()
        assert secret_model is None


class TestDeleteSecrets:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/delete",
            headers=get_auth_headers(user.token),
            json={"secrets_names": ["my_secret"]},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_secrets(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        # Create two secrets
        await create_secret(session=session, project=project, name="secret1", value="123456")
        await create_secret(session=session, project=project, name="secret2", value="abcdef")

        # Verify both secrets exist
        res = await session.execute(
            select(SecretModel).where(SecretModel.project_id == project.id)
        )
        secrets = res.scalars().all()
        assert len(secrets) == 2

        # Delete one secret
        response = await client.post(
            f"/api/project/{project.name}/secrets/delete",
            headers=get_auth_headers(user.token),
            json={"secrets_names": ["secret1"]},
        )
        assert response.status_code == 200

        # Verify only one secret remains
        res = await session.execute(
            select(SecretModel).where(SecretModel.project_id == project.id)
        )
        secrets = res.scalars().all()
        assert len(secrets) == 1
        assert secrets[0].name == "secret2"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_delete_nonexistent_secret_raises_error(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/secrets/delete",
            headers=get_auth_headers(user.token),
            json={"secrets_names": ["nonexistent_secret"]},
        )
        assert response.status_code == 400  # ResourceNotExistsError should return 404
