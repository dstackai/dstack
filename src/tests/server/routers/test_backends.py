import json
from unittest.mock import patch

import botocore.exceptions
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import BackendModel
from dstack._internal.server.services.projects import add_project_member
from tests.server.common import create_backend, create_project, create_user, get_auth_headers

client = TestClient(app)


class TestListBackendTypes:
    def test_returns_backend_types(self):
        response = client.post("/api/backends/list_types")
        assert response.status_code == 200, response.json()
        assert response.json() == ["aws"]


class TestGetBackendConfigValues:
    @pytest.mark.asyncio
    async def test_aws_returns_initial_config(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {"type": "aws"}
        response = client.post(
            "/api/backends/config_values",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "aws",
            "default_creds": False,
            "regions": None,
        }

    @pytest.mark.asyncio
    async def test_aws_returns_invalid_credentials(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
        }
        with patch("boto3.session.Session") as session_mock:
            session_mock.return_value.client.return_value.get_caller_identity.side_effect = (
                botocore.exceptions.ClientError({}, "")
            )
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            session_mock.assert_called()
        assert response.status_code == 400
        assert response.json() == {
            "detail": [
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "access_key"],
                },
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "secret_key"],
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_aws_returns_config_on_credentials(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
        }
        with patch("boto3.session.Session") as session_mock:
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            session_mock.assert_called()
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "aws",
            "default_creds": False,
            "regions": {
                "selected": ["us-east-1"],
                "values": [
                    {"label": "us-east-1", "value": "us-east-1"},
                    {"label": "us-east-2", "value": "us-east-2"},
                    {"label": "us-west-1", "value": "us-west-1"},
                    {"label": "us-west-2", "value": "us-west-2"},
                    {"label": "ap-southeast-1", "value": "ap-southeast-1"},
                    {"label": "ca-central-1", "value": "ca-central-1"},
                    {"label": "eu-central-1", "value": "eu-central-1"},
                    {"label": "eu-west-1", "value": "eu-west-1"},
                    {"label": "eu-west-2", "value": "eu-west-2"},
                    {"label": "eu-west-3", "value": "eu-west-3"},
                    {"label": "eu-north-1", "value": "eu-north-1"},
                ],
            },
        }


class TestCreateBackend:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/create",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_aws_creates_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-west-1"],
        }
        with patch("boto3.session.Session"):
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1


class TestUpdateBackend:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/update",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_updates_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(
            session=session, project_id=project.id, config={"regions": "us-west-1"}
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-east-1"],
        }
        with patch("boto3.session.Session"):
            response = client.post(
                f"/api/project/{project.name}/backends/update",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        await session.refresh(backend)
        assert json.loads(backend.config)["regions"] == ["us-east-1"]


class TestDeleteBackends:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_deletes_backends(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session=session, project_id=project.id)
        response = client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
            json={"backends_names": [backend.type.value]},
        )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 0


class TestGetConfigInfo:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/{backend.type.value}/config_info",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_config_info(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/backends/{backend.type.value}/config_info",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "aws",
            "regions": json.loads(backend.config)["regions"],
            "creds": json.loads(backend.auth),
        }
