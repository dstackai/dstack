import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import ProjectRole
from dstack._internal.server.db import reuse_or_make_session
from dstack._internal.server.main import app
from dstack._internal.server.services.projects import add_project_member
from tests.server.common import create_project, create_user, get_auth_headers

client = TestClient(app)


class TestListProjects:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, test_db, session):
        user = await create_user(session=session)
        response = client.post("/api/projects/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_projects(self, test_db, session):
        user = await create_user(session=session)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post("/api/projects/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == [{}]
