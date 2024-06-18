import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import VolumeModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_project,
    create_user,
    create_volume,
    get_auth_headers,
    get_volume_configuration,
)

client = TestClient(app)


class TestListVolumes:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/volumes/list")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_lists_volumes(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        volume = await create_volume(
            session=session,
            project=project,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = client.post(
            f"/api/project/{project.name}/volumes/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "name": volume.name,
                "configuration": json.loads(volume.configuration),
                "created_at": "2023-01-02T03:04:00+00:00",
                "status": "submitted",
                "status_message": None,
                "volume_id": None,
            }
        ]


class TestGetVolume:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/volumes/get")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_volume(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        volume = await create_volume(
            session=session,
            project=project,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = client.post(
            f"/api/project/{project.name}/volumes/get",
            headers=get_auth_headers(user.token),
            json={"name": volume.name},
        )
        assert response.status_code == 200
        assert response.json() == {
            "name": volume.name,
            "configuration": json.loads(volume.configuration),
            "created_at": "2023-01-02T03:04:00+00:00",
            "status": "submitted",
            "status_message": None,
            "volume_id": None,
        }

    @pytest.mark.asyncio
    async def test_returns_400_if_volume_does_not_exist(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/volumes/get",
            headers=get_auth_headers(user.token),
            json={"name": "some_volume"},
        )
        assert response.status_code == 400


class TestCreateVolume:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/volumes/create")
        assert response.status_code == 403

    @pytest.mark.asyncio
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_volume(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        configuration = get_volume_configuration(backend=BackendType.AWS)
        response = client.post(
            f"/api/project/{project.name}/volumes/create",
            headers=get_auth_headers(user.token),
            json={"configuration": configuration.dict()},
        )
        assert response.status_code == 200
        assert (
            response.json()
            == response.json()
            == {
                "name": configuration.name,
                "configuration": configuration,
                "created_at": "2023-01-02T03:04:00+00:00",
                "status": "submitted",
                "status_message": None,
                "volume_id": None,
            }
        )
        res = await session.execute(select(VolumeModel))
        assert res.scalar_one()


class TestDeleteVolumes:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/volumes/delete")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_deletes_volumes(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        volume = await create_volume(
            session=session,
            project=project,
        )
        response = client.post(
            f"/api/project/{project.name}/volumes/delete",
            headers=get_auth_headers(user.token),
            json={"names": [volume.name]},
        )
        assert response.status_code == 200
        await session.refresh(volume)
        assert volume.deleted

    # TODO: test cannot delete volume in use
