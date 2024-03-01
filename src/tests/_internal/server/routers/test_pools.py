import datetime as dt

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import PoolModel
from dstack._internal.server.schemas.pools import (
    CreatePoolRequest,
    DeletePoolRequest,
    RemoveInstanceRequest,
    SetDefaultPoolRequest,
    ShowPoolRequest,
)
from dstack._internal.server.schemas.runs import AddRemoteInstanceRequest
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_instance,
    create_pool,
    create_project,
    create_user,
    get_auth_headers,
)

client = TestClient(app)

TEST_POOL_NAME = "test_router_pool_name"


class TestListPool:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_authenticated(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/pool/list",
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @freeze_time(dt.datetime(2023, 10, 4, 12, 0, tzinfo=dt.timezone.utc))
    async def test_creates_and_lists_default_pool(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/pool/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200
        result = response.json()
        expected = [
            {
                "name": "default-pool",
                "default": True,
                "created_at": "2023-10-04T12:00:00+00:00",
                "total_instances": 0,
                "available_instances": 0,
            }
        ]
        assert result == expected


class TestDeletePool:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_authenticated(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/pool/delete",
            json=DeletePoolRequest(name=TEST_POOL_NAME, force=False).dict(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_last_pool(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        pool = await create_pool(session, project, pool_name=TEST_POOL_NAME)
        response = client.post(
            f"/api/project/{project.name}/pool/delete",
            headers=get_auth_headers(user.token),
            json=DeletePoolRequest(name=TEST_POOL_NAME, force=False).dict(),
        )
        assert response.status_code == 200
        assert response.json() is None

        response = client.post(
            f"/api/project/{project.name}/pool/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200

        result = response.json()
        assert len(result) == 1

        default_pool = result[0]
        assert default_pool["name"] == DEFAULT_POOL_NAME
        assert dt.datetime.fromisoformat(default_pool["created_at"]) > pool.created_at

    @pytest.mark.asyncio
    async def test_deletes_pool(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        pool1 = await create_pool(session, project, pool_name=f"{TEST_POOL_NAME}-left")
        pool2 = await create_pool(session, project, pool_name=f"{TEST_POOL_NAME}-right")
        response = client.post(
            f"/api/project/{project.name}/pool/delete",
            headers=get_auth_headers(user.token),
            json=DeletePoolRequest(name=pool1.name, force=False).dict(),
        )
        assert response.status_code == 200
        assert response.json() is None
        res = await session.execute(select(PoolModel).where(PoolModel.deleted == False))
        pool = res.scalar_one()
        assert pool.name == pool2.name

    @pytest.mark.asyncio
    async def test_returns_400_if_pool_missing(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/pool/delete",
            headers=get_auth_headers(user.token),
            json=DeletePoolRequest(name="missing name", force=False).dict(),
        )
        assert response.status_code == 400


class TestSetDefaultPool:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_authenticated(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/pool/set_default",
            json=SetDefaultPoolRequest(pool_name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_sets_default(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        pool = await create_pool(session, project, pool_name=f"{TEST_POOL_NAME}-right")
        response = client.post(
            f"/api/project/{project.name}/pool/set_default",
            headers=get_auth_headers(user.token),
            json=SetDefaultPoolRequest(pool_name=pool.name).dict(),
        )
        assert response.status_code == 200
        await session.refresh(project)
        assert project.default_pool_id == pool.id

    @pytest.mark.asyncio
    async def test_returns_400_if_pool_missing(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/pool/set_default",
            headers=get_auth_headers(user.token),
            json=SetDefaultPoolRequest(pool_name="missing pool").dict(),
        )
        assert response.status_code == 400


class TestCreatePool:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_authenticated(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/pool/create",
            json=CreatePoolRequest(name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_pool(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/pool/create",
            headers=get_auth_headers(user.token),
            json=CreatePoolRequest(name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 200
        assert response.json() is None
        res = await session.execute(select(PoolModel).where(PoolModel.deleted == False))
        res.scalar_one()

    @pytest.mark.asyncio
    async def test_returns_400_on_duplicate_name(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/pool/create",
            headers=get_auth_headers(user.token),
            json=CreatePoolRequest(name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 200
        assert response.json() is None
        response = client.post(
            f"/api/project/{project.name}/pool/create",
            headers=get_auth_headers(user.token),
            json=CreatePoolRequest(name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 400


class TestShowPool:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_authenticated(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/pool/show",
            json=CreatePoolRequest(name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_show_pool(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        pool = await create_pool(session, project, pool_name=TEST_POOL_NAME)
        await create_instance(session, project, pool)

        response = client.post(
            f"/api/project/{project.name}/pool/show",
            headers=get_auth_headers(user.token),
            json=ShowPoolRequest(name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 200
        assert response.json() == {
            "name": "test_router_pool_name",
            "instances": [
                {
                    "backend": "datacrunch",
                    "instance_type": {
                        "name": "instance",
                        "resources": {
                            "cpus": 1,
                            "memory_mib": 512,
                            "gpus": [],
                            "spot": False,
                            "disk": {"size_mib": 102400},
                            "description": "",
                        },
                    },
                    "name": "test_instance",
                    "job_name": None,
                    "job_status": None,
                    "hostname": "running_instance.ip",
                    "status": "ready",
                    "created": "2023-01-02T03:04:00+00:00",
                    "region": "en",
                    "price": 0.1,
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_show_missing_pool(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        pool = await create_pool(session, project, pool_name=TEST_POOL_NAME)
        await create_instance(session, project, pool)

        response = client.post(
            f"/api/project/{project.name}/pool/show",
            headers=get_auth_headers(user.token),
            json=ShowPoolRequest(name="missing_pool").dict(),
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": [{"msg": "Pool not found", "code": "resource_not_exists"}]
        }


class TestAddRemote:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_authenticated(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        remote = AddRemoteInstanceRequest(
            instance_name="test_instance_name",
            host="localhost",
            port="22",
            resources=ResourcesSpec(cpu=1),
            profile=Profile(name="test_profile"),
        )
        response = client.post(
            f"/api/project/{project.name}/pool/add_remote",
            json=remote.dict(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_add_remote(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        remote = AddRemoteInstanceRequest(
            instance_name="test_instance_name",
            host="localhost",
            port="22",
            resources=ResourcesSpec(cpu=1),
            profile=Profile(name="test_profile"),
        )
        response = client.post(
            f"/api/project/{project.name}/pool/add_remote",
            headers=get_auth_headers(user.token),
            json=remote.dict(),
        )
        assert response.status_code == 200
        assert response.json() == True


class TestRemoveInstance:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_authenticated(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        remote = AddRemoteInstanceRequest(
            instance_name="test_instance_name",
            host="localhost",
            port="22",
            resources=ResourcesSpec(cpu=1),
            profile=Profile(name="test_profile"),
        )
        response = client.post(
            f"/api/project/{project.name}/pool/add_remote",
            json=remote.dict(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_remove_instance(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        pool = await create_pool(session, project, pool_name=TEST_POOL_NAME)
        instance = await create_instance(session, project, pool)

        response = client.post(
            f"/api/project/{project.name}/pool/remove",
            headers=get_auth_headers(user.token),
            json=RemoveInstanceRequest(
                pool_name=TEST_POOL_NAME, instance_name=instance.name
            ).dict(),
        )
        assert response.status_code == 200
        assert response.json() is None

        response = client.post(
            f"/api/project/{project.name}/pool/show",
            headers=get_auth_headers(user.token),
            json=ShowPoolRequest(name=TEST_POOL_NAME).dict(),
        )
        assert response.status_code == 200
        assert response.json() == {
            "name": "test_router_pool_name",
            "instances": [
                {
                    "backend": "datacrunch",
                    "instance_type": {
                        "name": "instance",
                        "resources": {
                            "cpus": 1,
                            "memory_mib": 512,
                            "gpus": [],
                            "spot": False,
                            "disk": {"size_mib": 102400},
                            "description": "",
                        },
                    },
                    "name": "test_instance",
                    "job_name": None,
                    "job_status": None,
                    "hostname": "running_instance.ip",
                    "status": "terminating",
                    "created": "2023-01-02T03:04:00+00:00",
                    "region": "en",
                    "price": 0.1,
                }
            ],
        }
