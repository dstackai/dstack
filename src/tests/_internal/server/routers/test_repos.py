import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import CodeModel, RepoCredsModel, RepoModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_project,
    create_repo,
    create_repo_creds,
    create_user,
    get_auth_headers,
)


class TestListRepos:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/repos/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_empty_list(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/repos/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json() == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_repos(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/repos/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json() == [
            {
                "repo_id": repo.name,
                "repo_info": json.loads(repo.info),
            }
        ]


class TestGetRepo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/repos/get",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_repo_does_not_exist(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/repos/get",
            headers=get_auth_headers(user.token),
            json={"repo_id": "some_repo", "include_creds": False},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_repo(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/repos/get",
            headers=get_auth_headers(user.token),
            json={"repo_id": repo.name, "include_creds": False},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "repo_id": repo.name,
            "repo_info": json.loads(repo.info),
            "repo_creds": None,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_repo_with_legacy_creds(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        legacy_creds = {
            "clone_url": "https://github.com/dstackai/dstack.git",
            "private_key": None,
            "oauth_token": "test_token",
        }
        repo = await create_repo(session=session, project_id=project.id, creds=legacy_creds)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/repos/get",
            headers=get_auth_headers(user.token),
            json={"repo_id": repo.name, "include_creds": True},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "repo_id": repo.name,
            "repo_info": json.loads(repo.info),
            "repo_creds": legacy_creds,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_repo_with_user_creds(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        legacy_creds = {
            "clone_url": "https://github.com/dstackai/dstack.git",
            "private_key": None,
            "oauth_token": "legacy_creds",
        }
        repo = await create_repo(session=session, project_id=project.id, creds=legacy_creds)
        user_creds = {
            "clone_url": "https://github.com/dstackai/dstack.git",
            "private_key": None,
            "oauth_token": "user_creds",
        }
        await create_repo_creds(
            session=session, repo_id=repo.id, user_id=user.id, creds=user_creds
        )
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/repos/get",
            headers=get_auth_headers(user.token),
            json={"repo_id": repo.name, "include_creds": True},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "repo_id": repo.name,
            "repo_info": json.loads(repo.info),
            "repo_creds": user_creds,
        }


class TestInitRepo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/repos/init",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_remote_repo(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        body = {
            "repo_id": "test_repo",
            "repo_info": {
                "repo_type": "remote",
                "repo_name": "dstack",
            },
            "repo_creds": {
                "clone_url": "https://github.com/dstackai/dstack.git",
                "private_key": None,
                "oauth_token": "test_token",
            },
        }
        response = await client.post(
            f"/api/project/{project.name}/repos/init",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(RepoModel))
        repo = res.scalar_one()
        assert repo.name == body["repo_id"]
        assert json.loads(repo.info) == body["repo_info"]
        assert repo.creds is None
        res = await session.execute(select(RepoCredsModel))
        repo_creds = res.scalar_one()
        assert repo_creds.creds.plaintext is not None
        assert json.loads(repo_creds.creds.plaintext) == body["repo_creds"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_updates_remote_repo(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        body1 = {
            "repo_id": "test_repo",
            "repo_info": {
                "repo_type": "remote",
                "repo_name": "dstack",
            },
            "repo_creds": {
                "clone_url": "https://github.com/dstackai/dstack.git",
                "private_key": None,
                "oauth_token": "test_token",
            },
        }
        response = await client.post(
            f"/api/project/{project.name}/repos/init",
            headers=get_auth_headers(user.token),
            json=body1,
        )
        assert response.status_code == 200, response.json()
        body2 = {
            "repo_id": "test_repo",
            "repo_info": {
                "repo_type": "remote",
                "repo_name": "dstack",
            },
            "repo_creds": {
                "clone_url": "https://github.com/dstackai/dstack.git",
                "private_key": None,
                "oauth_token": "test_token_updated",
            },
        }
        response = await client.post(
            f"/api/project/{project.name}/repos/init",
            headers=get_auth_headers(user.token),
            json=body2,
        )
        res = await session.execute(select(RepoModel))
        repo = res.scalar_one()
        assert repo.creds is None
        res = await session.execute(select(RepoCredsModel))
        repo_creds = res.scalar_one()
        assert repo_creds.creds.plaintext is not None
        assert json.loads(repo_creds.creds.plaintext) == body2["repo_creds"]


class TestDeleteRepos:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/repos/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_repos(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        response = await client.post(
            f"/api/project/{project.name}/repos/delete",
            headers=get_auth_headers(user.token),
            json={"repos_ids": [repo.name]},
        )
        assert response.status_code == 200
        res = await session.execute(select(RepoModel))
        repo = res.scalar()
        assert repo is None


class TestUploadCode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/repos/upload_code",
            headers=get_auth_headers(user.token),
            params={"repo_id": "test_repo"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_uploads_code(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        file = ("blob_hash", b"blob_content")
        response = await client.post(
            f"/api/project/{project.name}/repos/upload_code",
            headers=get_auth_headers(user.token),
            params={"repo_id": repo.name},
            files={"file": file},
        )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(CodeModel))
        code = res.scalar()
        assert code.blob_hash == file[0]
        assert code.blob == file[1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_uploads_same_code_for_different_repos(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo1 = await create_repo(session=session, repo_name="repo1", project_id=project.id)
        repo2 = await create_repo(session=session, repo_name="repo2", project_id=project.id)
        file = ("blob_hash", b"blob_content")
        response = await client.post(
            f"/api/project/{project.name}/repos/upload_code",
            headers=get_auth_headers(user.token),
            params={"repo_id": repo1.name},
            files={"file": file},
        )
        assert response.status_code == 200, response.json()
        response = await client.post(
            f"/api/project/{project.name}/repos/upload_code",
            headers=get_auth_headers(user.token),
            params={"repo_id": repo2.name},
            files={"file": file},
        )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(CodeModel))
        codes = res.scalars().all()
        assert len(codes) == 2
