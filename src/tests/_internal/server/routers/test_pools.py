import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
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
    async def test_create_default_and_list(self, test_db, session: AsyncSession):
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
        assert len(result) == 1
        pool = result[0]
        expected = [
            {
                "name": "default-pool",
                "default": True,
                "created_at": str(pool["created_at"]),
                "total_instances": 0,
                "available_instances": 0,
            }
        ]
        assert result == expected

    @pytest.mark.asyncio
    async def test_list_pools(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )

        await create_pool(session, project, pool_name=TEST_POOL_NAME)

        response = client.post(
            f"/api/project/{project.name}/pool/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200

        result = response.json()
        assert len(result) == 1
        pool = result[0]
        expected = [
            {
                "name": TEST_POOL_NAME,
                "default": False,
                "created_at": str(pool["created_at"]),
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
    async def test_delete_pool(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        pool_left = await create_pool(session, project, pool_name=f"{TEST_POOL_NAME}-left")
        pool_right = await create_pool(session, project, pool_name=f"{TEST_POOL_NAME}-right")
        response = client.post(
            f"/api/project/{project.name}/pool/delete",
            headers=get_auth_headers(user.token),
            json=DeletePoolRequest(name=pool_left.name, force=False).dict(),
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
        assert default_pool["name"] == pool_right.name

    @pytest.mark.asyncio
    async def test_delete_missing(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        pool = await create_pool(session, project, pool_name=TEST_POOL_NAME)
        response = client.post(
            f"/api/project/{project.name}/pool/delete",
            headers=get_auth_headers(user.token),
            json=DeletePoolRequest(name="missing name", force=False).dict(),
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
        assert default_pool["name"] == pool.name


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
    async def test_set_default(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        await create_pool(session, project, pool_name=f"{TEST_POOL_NAME}-left")
        pool_right = await create_pool(session, project, pool_name=f"{TEST_POOL_NAME}-right")
        response = client.post(
            f"/api/project/{project.name}/pool/set_default",
            headers=get_auth_headers(user.token),
            json=SetDefaultPoolRequest(pool_name=pool_right.name).dict(),
        )
        assert response.status_code == 200
        assert response.json() == True

        response = client.post(
            f"/api/project/{project.name}/pool/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200

        result = response.json()
        assert len(result) == 2

        default_pool = [p for p in result if p["default"]][0]
        assert default_pool["name"] == pool_right.name

    @pytest.mark.asyncio
    async def test_set_default_missing(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        pool = await create_pool(session, project, pool_name=TEST_POOL_NAME)
        response = client.post(
            f"/api/project/{project.name}/pool/set_default",
            headers=get_auth_headers(user.token),
            json=SetDefaultPoolRequest(pool_name="missing pool").dict(),
        )
        assert response.status_code == 200
        assert response.json() == False

        response = client.post(
            f"/api/project/{project.name}/pool/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200

        result = response.json()
        assert len(result) == 1

        result_pool = result[0]
        assert result_pool["name"] == pool.name
        assert result_pool["default"] == False


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

        response = client.post(
            f"/api/project/{project.name}/pool/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200

        result = response.json()
        assert len(result) == 1

        default_pool = result[0]
        assert default_pool["name"] == TEST_POOL_NAME

    @pytest.mark.asyncio
    async def test_duplicate_name(self, test_db, session: AsyncSession):
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

        with pytest.raises(ValueError):
            response = client.post(
                f"/api/project/{project.name}/pool/create",
                headers=get_auth_headers(user.token),
                json=CreatePoolRequest(name=TEST_POOL_NAME).dict(),
            )


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
                    "created": "2023-01-02T03:04:00",
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
            "detail": [{"msg": "Pool is not found", "code": "resource_not_exists"}]
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
                    "created": "2023-01-02T03:04:00",
                    "region": "en",
                    "price": 0.1,
                }
            ],
        }
