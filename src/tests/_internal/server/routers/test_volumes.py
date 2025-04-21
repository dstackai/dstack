import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import UUID

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import VolumeAttachmentModel, VolumeModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_instance,
    create_project,
    create_user,
    create_volume,
    get_auth_headers,
    get_volume_configuration,
    get_volume_provisioning_data,
)


class TestListVolumes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        response = await client.post("/api/volumes/list")
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_lists_volumes_across_projects(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.ADMIN)
        project1 = await create_project(session, name="project1", owner=user)
        volume1 = await create_volume(
            session=session,
            project=project1,
            user=user,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            configuration=get_volume_configuration(name="volume1"),
        )
        project2 = await create_project(session, name="project2", owner=user)
        volume2 = await create_volume(
            session=session,
            project=project2,
            user=user,
            created_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
            configuration=get_volume_configuration(name="volume2"),
        )
        response = await client.post(
            "/api/volumes/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == [
            {
                "id": str(volume2.id),
                "name": volume2.name,
                "project_name": project2.name,
                "user": user.name,
                "configuration": json.loads(volume2.configuration),
                "external": False,
                "created_at": "2023-01-02T03:05:00+00:00",
                "last_processed_at": "2023-01-02T03:05:00+00:00",
                "status": "submitted",
                "status_message": None,
                "deleted": False,
                "deleted_at": None,
                "volume_id": None,
                "provisioning_data": None,
                "cost": 0.0,
                "attachments": [],
                "attachment_data": None,
            },
            {
                "id": str(volume1.id),
                "name": volume1.name,
                "project_name": project1.name,
                "user": user.name,
                "configuration": json.loads(volume1.configuration),
                "external": False,
                "created_at": "2023-01-02T03:04:00+00:00",
                "last_processed_at": "2023-01-02T03:04:00+00:00",
                "status": "submitted",
                "status_message": None,
                "deleted": False,
                "deleted_at": None,
                "volume_id": None,
                "provisioning_data": None,
                "cost": 0.0,
                "attachments": [],
                "attachment_data": None,
            },
        ]
        response = await client.post(
            "/api/volumes/list",
            headers=get_auth_headers(user.token),
            json={
                "prev_created_at": "2023-01-02T03:05:00+00:00",
                "prev_id": str(volume2.id),
            },
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(volume1.id),
                "name": volume1.name,
                "project_name": project1.name,
                "user": user.name,
                "configuration": json.loads(volume1.configuration),
                "external": False,
                "created_at": "2023-01-02T03:04:00+00:00",
                "last_processed_at": "2023-01-02T03:04:00+00:00",
                "status": "submitted",
                "status_message": None,
                "deleted": False,
                "deleted_at": None,
                "volume_id": None,
                "provisioning_data": None,
                "cost": 0.0,
                "attachments": [],
                "attachment_data": None,
            },
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_non_admin_cannot_see_others_projects(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user1 = await create_user(session, name="user1", global_role=GlobalRole.USER)
        user2 = await create_user(session, name="user2", global_role=GlobalRole.USER)
        project1 = await create_project(session, name="project1", owner=user1)
        project2 = await create_project(session, name="project2", owner=user2)
        await add_project_member(
            session=session, project=project1, user=user1, project_role=ProjectRole.USER
        )
        await add_project_member(
            session=session, project=project2, user=user2, project_role=ProjectRole.USER
        )
        volume1 = await create_volume(
            session=session,
            project=project1,
            user=user1,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            configuration=get_volume_configuration(name="volume1"),
        )
        await create_volume(
            session=session,
            project=project2,
            user=user2,
            created_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
            configuration=get_volume_configuration(name="volume2"),
        )
        response = await client.post(
            "/api/volumes/list",
            headers=get_auth_headers(user1.token),
            json={},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == [
            {
                "id": str(volume1.id),
                "name": volume1.name,
                "project_name": project1.name,
                "user": user1.name,
                "configuration": json.loads(volume1.configuration),
                "external": False,
                "created_at": "2023-01-02T03:04:00+00:00",
                "last_processed_at": "2023-01-02T03:04:00+00:00",
                "status": "submitted",
                "status_message": None,
                "deleted": False,
                "deleted_at": None,
                "volume_id": None,
                "provisioning_data": None,
                "cost": 0.0,
                "attachments": [],
                "attachment_data": None,
            },
        ]


class TestListProjectVolumes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        response = await client.post("/api/project/main/volumes/list")
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_lists_volumes(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = await client.post(
            f"/api/project/{project.name}/volumes/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(volume.id),
                "name": volume.name,
                "project_name": project.name,
                "user": user.name,
                "configuration": json.loads(volume.configuration),
                "external": False,
                "created_at": "2023-01-02T03:04:00+00:00",
                "last_processed_at": "2023-01-02T03:04:00+00:00",
                "status": "submitted",
                "status_message": None,
                "deleted": False,
                "deleted_at": None,
                "volume_id": None,
                "provisioning_data": None,
                "cost": 0.0,
                "attachments": [],
                "attachment_data": None,
            }
        ]


class TestGetVolume:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        response = await client.post("/api/project/main/volumes/get")
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_volume(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = await client.post(
            f"/api/project/{project.name}/volumes/get",
            headers=get_auth_headers(user.token),
            json={"name": volume.name},
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": str(volume.id),
            "name": volume.name,
            "project_name": project.name,
            "user": user.name,
            "configuration": json.loads(volume.configuration),
            "external": False,
            "created_at": "2023-01-02T03:04:00+00:00",
            "last_processed_at": "2023-01-02T03:04:00+00:00",
            "status": "submitted",
            "status_message": None,
            "deleted": False,
            "deleted_at": None,
            "volume_id": None,
            "provisioning_data": None,
            "cost": 0.0,
            "attachments": [],
            "attachment_data": None,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_volume_does_not_exist(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/volumes/get",
            headers=get_auth_headers(user.token),
            json={"name": "some_volume"},
        )
        assert response.status_code == 400


class TestCreateVolume:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        response = await client.post("/api/project/main/volumes/create")
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_volume(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        configuration = get_volume_configuration(backend=BackendType.AWS)
        with patch("uuid.uuid4") as m:
            m.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = await client.post(
                f"/api/project/{project.name}/volumes/create",
                headers=get_auth_headers(user.token),
                json={"configuration": configuration.dict()},
            )
        assert response.status_code == 200
        assert response.json() == {
            "id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
            "name": configuration.name,
            "project_name": project.name,
            "configuration": configuration,
            "user": user.name,
            "external": False,
            "created_at": "2023-01-02T03:04:00+00:00",
            "last_processed_at": "2023-01-02T03:04:00+00:00",
            "status": "submitted",
            "status_message": None,
            "deleted": False,
            "deleted_at": None,
            "volume_id": None,
            "provisioning_data": None,
            "cost": 0.0,
            "attachments": [],
            "attachment_data": None,
        }
        res = await session.execute(select(VolumeModel))
        assert res.scalar_one()


class TestDeleteVolumes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        response = await client.post("/api/project/main/volumes/delete")
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_volumes(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            volume_provisioning_data=get_volume_provisioning_data(),
        )
        with patch(
            "dstack._internal.server.services.backends.get_project_backend_by_type_or_error"
        ) as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            response = await client.post(
                f"/api/project/{project.name}/volumes/delete",
                headers=get_auth_headers(user.token),
                json={"names": [volume.name]},
            )
            aws_mock.compute.return_value.delete_volume.assert_called()
        assert response.status_code == 200
        await session.refresh(volume)
        assert volume.deleted

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_when_volumes_in_use(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            volume_provisioning_data=get_volume_provisioning_data(),
        )
        instance = await create_instance(
            session=session,
            project=project,
        )
        volume.attachments.append(VolumeAttachmentModel(instance=instance))
        await session.commit()
        response = await client.post(
            f"/api/project/{project.name}/volumes/delete",
            headers=get_auth_headers(user.token),
            json={"names": [volume.name]},
        )
        assert response.status_code == 400
        await session.refresh(volume)
        assert not volume.deleted
