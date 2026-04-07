import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.models import ProjectModel, RepoModel, UserModel
from dstack._internal.server.testing.common import create_project, create_repo, create_user


async def _count_rows(session: AsyncSession, model) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.parametrize("test_db", ["postgres"], indirect=True)
async def test_postgres_fixture_allows_creating_related_rows(test_db, session: AsyncSession):
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    await create_repo(session=session, project_id=project.id)

    assert await _count_rows(session, UserModel) == 1
    assert await _count_rows(session, ProjectModel) == 1
    assert await _count_rows(session, RepoModel) == 1


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.parametrize("test_db", ["postgres"], indirect=True)
async def test_postgres_fixture_starts_next_test_empty(test_db, session: AsyncSession):
    assert await _count_rows(session, UserModel) == 0
    assert await _count_rows(session, ProjectModel) == 0
    assert await _count_rows(session, RepoModel) == 0

    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    await create_repo(session=session, project_id=project.id)

    assert await _count_rows(session, UserModel) == 1
    assert await _count_rows(session, ProjectModel) == 1
    assert await _count_rows(session, RepoModel) == 1
