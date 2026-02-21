from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services import templates as templates_service
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_project,
    create_user,
    get_auth_headers,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the templates cache before each test."""
    templates_service._templates_cache.clear()
    templates_service._repo_path = None
    yield
    templates_service._templates_cache.clear()
    templates_service._repo_path = None


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/project/test_project/templates/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_repo(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        with patch.object(templates_service.settings, "SERVER_TEMPLATES_REPO", None):
            response = await client.post(
                f"/api/project/{project.name}/templates/list",
                headers=get_auth_headers(user.token),
            )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_templates(
        self, test_db, session: AsyncSession, client: AsyncClient, tmp_path: Path
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        templates_dir = tmp_path / ".dstack" / "templates"
        templates_dir.mkdir(parents=True)
        for filename, data in [
            (
                "desktop-ide.yml",
                {
                    "type": "ui-template",
                    "id": "desktop-ide",
                    "title": "Desktop IDE",
                    "parameters": [{"type": "name"}, {"type": "ide"}],
                    "template": {"type": "dev-environment"},
                },
            ),
            (
                "web-based-ide.yml",
                {
                    "type": "ui-template",
                    "id": "web-based-ide",
                    "title": "Web-based IDE",
                    "parameters": [
                        {"type": "name"},
                        {
                            "type": "env",
                            "title": "Password",
                            "name": "PASSWORD",
                            "value": "$random-password",
                        },
                    ],
                    "template": {"type": "service", "port": 8080},
                },
            ),
        ]:
            with open(templates_dir / filename, "w") as f:
                yaml.dump(data, f)

        with (
            patch.object(
                templates_service.settings, "SERVER_TEMPLATES_REPO", "https://example.com"
            ),
            patch.object(templates_service, "_fetch_templates_repo"),
        ):
            templates_service._repo_path = tmp_path
            response = await client.post(
                f"/api/project/{project.name}/templates/list",
                headers=get_auth_headers(user.token),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "desktop-ide"
        assert data[0]["template"]["type"] == "dev-environment"
        assert data[1]["id"] == "web-based-ide"
        assert data[1]["parameters"][1]["type"] == "env"
        assert data[1]["parameters"][1]["name"] == "PASSWORD"
        assert data[1]["template"]["port"] == 8080
