from typing import Optional
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.repos import RemoteRepoCreds, RemoteRepoInfo, RepoHeadWithCreds
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import ProjectModel, RepoCredsModel, UserModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.services.repos import get_repo, init_repo
from dstack._internal.server.testing.common import (
    create_project,
    create_repo,
    create_repo_creds,
    create_user,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("test_db"),
    pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True),
]


_REPO_ID = "test-36senvbc"


async def _create_user(session: AsyncSession, project: ProjectModel, name: str) -> UserModel:
    user = await create_user(session=session, name=name, global_role=GlobalRole.USER)
    await add_project_member(
        session=session, project=project, user=user, project_role=ProjectRole.USER
    )
    return user


async def _get_repo_creds(
    session: AsyncSession, repo_id: UUID, user_id: UUID
) -> Optional[RemoteRepoCreds]:
    res = await session.execute(select(RepoCredsModel).filter_by(repo_id=repo_id, user_id=user_id))
    repo_creds = res.scalar()
    if repo_creds is None:
        return None
    creds_raw = repo_creds.creds.plaintext
    assert creds_raw is not None
    return RemoteRepoCreds.parse_raw(creds_raw)


@pytest_asyncio.fixture
async def project(session: AsyncSession) -> ProjectModel:
    owner = await create_user(session=session, name="project-admin", global_role=GlobalRole.USER)
    project = await create_project(session=session, owner=owner, name="our-project")
    await add_project_member(
        session=session, project=project, user=owner, project_role=ProjectRole.ADMIN
    )
    return project


@pytest_asyncio.fixture
async def user(session: AsyncSession, project: ProjectModel) -> UserModel:
    return await _create_user(session, project, name="default-user")


class TestGetRemoteRepo:
    async def test_returns_none_if_repo_not_found(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        another_project = await create_project(session=session, owner=user, name="another-project")
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        # a repo with the same project_id in another project, should be ignored
        await create_repo(
            session=session,
            project_id=another_project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=repo_info.dict(),
        )

        repo = await get_repo(
            session=session, project=project, user=user, repo_id=_REPO_ID, include_creds=False
        )

        assert repo is None

    async def test_returns_repo_with_none_creds_if_include_creds_is_false(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        legacy_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="legacy-oauth-token",
        )
        repo_model = await create_repo(
            session=session,
            project_id=project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=repo_info.dict(),
            creds=legacy_repo_creds.dict(),
        )
        user_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="user-oauth-token",
        )
        await create_repo_creds(
            session=session,
            repo_id=repo_model.id,
            user_id=user.id,
            creds=user_repo_creds.dict(),
        )

        repo = await get_repo(
            session=session, project=project, user=user, repo_id=_REPO_ID, include_creds=False
        )

        assert repo == RepoHeadWithCreds(
            repo_id=_REPO_ID,
            repo_info=repo_info,
            # both legacy and user creds are ignored
            repo_creds=None,
        )

    async def test_returns_repo_with_none_creds_if_no_user_or_legacy_creds(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        repo_model = await create_repo(
            session=session,
            project_id=project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=repo_info.dict(),
            creds=None,
        )
        # another user's creds should be ignored
        another_user = await _create_user(session, project, name="another-user")
        another_user_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="another-oauth-token",
        )
        await create_repo_creds(
            session=session,
            repo_id=repo_model.id,
            user_id=another_user.id,
            creds=another_user_repo_creds.dict(),
        )

        repo = await get_repo(
            session=session,
            project=project,
            user=user,
            repo_id=_REPO_ID,
            include_creds=True,
        )

        assert repo == RepoHeadWithCreds(
            repo_id=_REPO_ID,
            repo_info=repo_info,
            repo_creds=None,
        )

    @pytest.mark.parametrize(
        "with_legacy_creds",
        [
            pytest.param(False, id="without-legacy-creds"),
            pytest.param(True, id="with-legacy-creds"),
        ],
    )
    async def test_returns_repo_with_user_creds_if_present(
        self,
        session: AsyncSession,
        project: ProjectModel,
        user: UserModel,
        with_legacy_creds: bool,
    ):
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        if with_legacy_creds:
            legacy_repo_creds = RemoteRepoCreds(
                clone_url="https://git.example.com/repo.git",
                private_key=None,
                oauth_token="legacy-oauth-token",
            )
        else:
            legacy_repo_creds = None
        repo_model = await create_repo(
            session=session,
            project_id=project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=repo_info.dict(),
            creds=legacy_repo_creds.dict() if legacy_repo_creds else None,
        )
        user_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="user-oauth-token",
        )
        await create_repo_creds(
            session=session,
            repo_id=repo_model.id,
            user_id=user.id,
            creds=user_repo_creds.dict(),
        )

        repo = await get_repo(
            session=session, project=project, user=user, repo_id=_REPO_ID, include_creds=True
        )

        assert repo == RepoHeadWithCreds(
            repo_id=_REPO_ID,
            repo_info=repo_info,
            repo_creds=user_repo_creds,
        )

    async def test_returns_repo_with_legacy_creds_if_user_creds_not_found(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        legacy_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="legacy-oauth-token",
        )
        await create_repo(
            session=session,
            project_id=project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=repo_info.dict(),
            creds=legacy_repo_creds.dict(),
        )

        repo = await get_repo(
            session=session, project=project, user=user, repo_id=_REPO_ID, include_creds=True
        )

        assert repo == RepoHeadWithCreds(
            repo_id=_REPO_ID,
            repo_info=repo_info,
            repo_creds=legacy_repo_creds,
        )


class TestInitRemoteRepo:
    async def test_creates_new_repo_with_user_creds(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="oauth-token",
        )

        repo = await init_repo(
            session=session,
            project=project,
            user=user,
            repo_id=_REPO_ID,
            repo_info=repo_info,
            repo_creds=repo_creds,
        )

        assert repo.creds is None
        assert await _get_repo_creds(session, repo.id, user.id) == repo_creds

    async def test_updates_repo_adding_user_creds(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        old_repo_info = RemoteRepoInfo(repo_type="remote", repo_name="old-name")
        new_repo_info = RemoteRepoInfo(repo_type="remote", repo_name="new-name")
        our_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="our-oauth-token",
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=old_repo_info.dict(),
            creds=None,
        )

        repo = await init_repo(
            session=session,
            project=project,
            user=user,
            repo_id=_REPO_ID,
            repo_info=new_repo_info,
            repo_creds=our_repo_creds,
        )

        assert repo.creds is None
        assert RemoteRepoInfo.parse_raw(repo.info) == new_repo_info
        assert await _get_repo_creds(session, repo.id, user.id) == our_repo_creds

    async def test_updates_repo_updating_user_creds(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        repo = await create_repo(
            session=session,
            project_id=project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=repo_info.dict(),
            creds=None,
        )
        old_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="oauth-token",
        )
        await create_repo_creds(
            session=session,
            repo_id=repo.id,
            user_id=user.id,
            creds=old_repo_creds.dict(),
        )
        new_repo_creds = RemoteRepoCreds(
            clone_url="ssh://git@git.example.com/repo.git",
            private_key="private-key",
            oauth_token=None,
        )

        repo = await init_repo(
            session=session,
            project=project,
            user=user,
            repo_id=_REPO_ID,
            repo_info=repo_info,
            repo_creds=new_repo_creds,
        )

        assert await _get_repo_creds(session, repo.id, user.id) == new_repo_creds

    async def test_updates_repo_removing_user_creds(
        self, session: AsyncSession, project: ProjectModel, user: UserModel
    ):
        repo_info = RemoteRepoInfo(repo_type="remote", repo_name="test")
        legacy_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="legacy-oauth-token",
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
            repo_name=_REPO_ID,
            repo_type=RepoType.REMOTE,
            info=repo_info.dict(),
            creds=legacy_repo_creds.dict(),
        )
        our_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="our-oauth-token",
        )
        await create_repo_creds(
            session=session,
            repo_id=repo.id,
            user_id=user.id,
            creds=our_repo_creds.dict(),
        )
        another_user = await _create_user(session, project, name="another-user")
        another_user_repo_creds = RemoteRepoCreds(
            clone_url="https://git.example.com/repo.git",
            private_key=None,
            oauth_token="another-oauth-token",
        )
        await create_repo_creds(
            session=session,
            repo_id=repo.id,
            user_id=another_user.id,
            creds=another_user_repo_creds.dict(),
        )

        repo = await init_repo(
            session=session,
            project=project,
            user=user,
            repo_id=_REPO_ID,
            repo_info=repo_info,
            repo_creds=None,
        )

        # legacy creds stored in the repo are still here
        assert repo.creds is not None
        assert RemoteRepoCreds.parse_raw(repo.creds) == legacy_repo_creds
        # our personal creds are deleted
        assert await _get_repo_creds(session, repo.id, user.id) is None
        # another user's creds are still here
        assert await _get_repo_creds(session, repo.id, another_user.id) == another_user_repo_creds
