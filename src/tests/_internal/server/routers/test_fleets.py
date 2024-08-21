import json
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.fleets import FleetConfiguration, FleetStatus, SSHParams
from dstack._internal.core.models.instances import InstanceStatus, SSHKey
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import FleetModel, InstanceModel
from dstack._internal.server.services.permissions import DefaultPermissions
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_job,
    create_pool,
    create_project,
    create_repo,
    create_run,
    create_user,
    default_permissions_context,
    get_auth_headers,
    get_fleet_configuration,
    get_fleet_spec,
)

client = TestClient(app)


class TestListFleets:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/fleets/list")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_lists_fleets(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        fleet = await create_fleet(
            session=session,
            project=project,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = client.post(
            f"/api/project/{project.name}/fleets/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "name": fleet.name,
                "project_name": project.name,
                "spec": json.loads(fleet.spec),
                "created_at": "2023-01-02T03:04:00+00:00",
                "status": fleet.status.value,
                "status_message": None,
                "instances": [],
            }
        ]


class TestGetFleet:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/fleets/get")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_fleet(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        fleet = await create_fleet(
            session=session,
            project=project,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        response = client.post(
            f"/api/project/{project.name}/fleets/get",
            headers=get_auth_headers(user.token),
            json={"name": fleet.name},
        )
        assert response.status_code == 200
        assert response.json() == {
            "name": fleet.name,
            "project_name": project.name,
            "spec": json.loads(fleet.spec),
            "created_at": "2023-01-02T03:04:00+00:00",
            "status": fleet.status.value,
            "status_message": None,
            "instances": [],
        }

    @pytest.mark.asyncio
    async def test_returns_400_if_fleet_does_not_exist(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/fleets/get",
            headers=get_auth_headers(user.token),
            json={"name": "some_fleet"},
        )
        assert response.status_code == 400


class TestCreateFleet:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/fleets/create")
        assert response.status_code == 403

    @pytest.mark.asyncio
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_fleet(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        spec = get_fleet_spec(conf=get_fleet_configuration())
        with patch("uuid.uuid4") as m:
            m.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = client.post(
                f"/api/project/{project.name}/fleets/create",
                headers=get_auth_headers(user.token),
                json={"spec": spec.dict()},
            )
        assert response.status_code == 200
        assert response.json() == {
            "name": spec.configuration.name,
            "project_name": project.name,
            "spec": {
                "configuration": {
                    "nodes": {"min": 1, "max": 1},
                    "placement": None,
                    "env": {},
                    "ssh_config": None,
                    "resources": {
                        "cpu": {"min": 2, "max": None},
                        "memory": {"min": 8.0, "max": None},
                        "shm_size": None,
                        "gpu": None,
                        "disk": {"size": {"min": 100.0, "max": None}},
                    },
                    "backends": None,
                    "regions": None,
                    "instance_types": None,
                    "spot_policy": None,
                    "retry": None,
                    "max_price": None,
                    "termination_policy": None,
                    "termination_idle_time": None,
                    "type": "fleet",
                    "name": "test-fleet",
                },
                "profile": {
                    "backends": None,
                    "regions": None,
                    "instance_types": None,
                    "spot_policy": None,
                    "retry": None,
                    "retry_policy": None,
                    "max_duration": None,
                    "max_price": None,
                    "pool_name": None,
                    "instance_name": None,
                    "creation_policy": None,
                    "termination_policy": None,
                    "termination_idle_time": None,
                    "name": "",
                    "default": False,
                },
                "autocreated": False,
            },
            "created_at": "2023-01-02T03:04:00+00:00",
            "status": "active",
            "status_message": None,
            "instances": [
                {
                    "id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
                    "project_name": project.name,
                    "name": f"{spec.configuration.name}-0",
                    "instance_num": 0,
                    "job_name": None,
                    "hostname": None,
                    "status": "pending",
                    "unreachable": False,
                    "created": "2023-01-02T03:04:00+00:00",
                    "pool_name": None,
                    "backend": None,
                    "region": None,
                    "instance_type": None,
                    "price": None,
                }
            ],
        }
        res = await session.execute(select(FleetModel))
        assert res.scalar_one()
        res = await session.execute(select(InstanceModel))
        assert res.scalar_one()

    @pytest.mark.asyncio
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_ssh_fleet(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        spec = get_fleet_spec(
            conf=FleetConfiguration(
                name="test-ssh-fleet",
                ssh_config=SSHParams(
                    user="ubuntu",
                    ssh_key=SSHKey(public="", private="123"),
                    hosts=["1.1.1.1"],
                    network=None,
                ),
            )
        )
        with patch("uuid.uuid4") as m:
            m.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = client.post(
                f"/api/project/{project.name}/fleets/create",
                headers=get_auth_headers(user.token),
                json={"spec": spec.dict()},
            )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "name": spec.configuration.name,
            "project_name": project.name,
            "spec": {
                "configuration": {
                    "env": {},
                    "ssh_config": {
                        "user": "ubuntu",
                        "port": None,
                        "identity_file": None,
                        "ssh_key": None,  # should not return ssh_key
                        "hosts": ["1.1.1.1"],
                        "network": None,
                    },
                    "nodes": None,
                    "placement": None,
                    "resources": {
                        "cpu": {"min": 2, "max": None},
                        "memory": {"min": 8.0, "max": None},
                        "shm_size": None,
                        "gpu": None,
                        "disk": {"size": {"min": 100.0, "max": None}},
                    },
                    "backends": None,
                    "regions": None,
                    "instance_types": None,
                    "spot_policy": None,
                    "retry": None,
                    "max_price": None,
                    "termination_policy": None,
                    "termination_idle_time": None,
                    "type": "fleet",
                    "name": spec.configuration.name,
                },
                "profile": {
                    "backends": None,
                    "regions": None,
                    "instance_types": None,
                    "spot_policy": None,
                    "retry": None,
                    "retry_policy": None,
                    "max_duration": None,
                    "max_price": None,
                    "pool_name": None,
                    "instance_name": None,
                    "creation_policy": None,
                    "termination_policy": None,
                    "termination_idle_time": None,
                    "name": "",
                    "default": False,
                },
                "autocreated": False,
            },
            "created_at": "2023-01-02T03:04:00+00:00",
            "status": "active",
            "status_message": None,
            "instances": [
                {
                    "id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
                    "project_name": project.name,
                    "backend": "remote",
                    "instance_type": {
                        "name": "ssh",
                        "resources": {
                            "cpus": 2,
                            "memory_mib": 8,
                            "gpus": [],
                            "spot": False,
                            "disk": {"size_mib": 102400},
                            "description": "",
                        },
                    },
                    "name": f"{spec.configuration.name}-0",
                    "instance_num": 0,
                    "pool_name": None,
                    "job_name": None,
                    "hostname": "1.1.1.1",
                    "status": "pending",
                    "unreachable": False,
                    "created": "2023-01-02T03:04:00+00:00",
                    "region": "remote",
                    "price": 0.0,
                }
            ],
        }
        res = await session.execute(select(FleetModel))
        assert res.scalar_one()
        res = await session.execute(select(InstanceModel))
        instance = res.scalar_one()
        assert instance.remote_connection_info is not None

    @pytest.mark.asyncio
    async def test_forbids_if_no_permission_to_manage_ssh_fleets(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        spec = get_fleet_spec(
            conf=FleetConfiguration(
                name="test-ssh-fleet",
                ssh_config=SSHParams(
                    user="ubuntu",
                    ssh_key=SSHKey(public="", private="123"),
                    hosts=["1.1.1.1"],
                    network=None,
                ),
            )
        )
        with default_permissions_context(
            DefaultPermissions(allow_non_admins_manage_ssh_fleets=False)
        ):
            response = client.post(
                f"/api/project/{project.name}/fleets/create",
                headers=get_auth_headers(user.token),
                json={"spec": spec.dict()},
            )
        assert response.status_code in [401, 403]


class TestDeleteFleets:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/fleets/delete")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_terminates_fleet_instances(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        pool = await create_pool(session=session, project=project)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
        )
        fleet.instances.append(instance)
        await session.commit()
        response = client.post(
            f"/api/project/{project.name}/fleets/delete",
            headers=get_auth_headers(user.token),
            json={"names": [fleet.name]},
        )
        assert response.status_code == 200
        await session.refresh(fleet)
        await session.refresh(instance)
        assert not fleet.deleted  # should not be deleted yet
        assert instance.status == InstanceStatus.TERMINATING

    @pytest.mark.asyncio
    async def test_returns_400_when_fleets_in_use(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        pool = await create_pool(session=session, project=project)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        fleet = await create_fleet(session=session, project=project)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
        )
        instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            status=InstanceStatus.BUSY,
            job=job,
        )
        fleet.instances.append(instance)
        await session.commit()
        response = client.post(
            f"/api/project/{project.name}/fleets/delete",
            headers=get_auth_headers(user.token),
            json={"names": [fleet.name]},
        )
        assert response.status_code == 400
        await session.refresh(fleet)
        assert not fleet.deleted
        assert instance.status == InstanceStatus.BUSY

    @pytest.mark.asyncio
    async def test_forbids_if_no_permission_to_manage_ssh_fleets(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        spec = get_fleet_spec(
            conf=FleetConfiguration(
                name="test-ssh-fleet",
                ssh_config=SSHParams(
                    user="ubuntu",
                    ssh_key=SSHKey(public="", private="123"),
                    hosts=["1.1.1.1"],
                    network=None,
                ),
            )
        )
        fleet = await create_fleet(session=session, project=project, spec=spec)
        with default_permissions_context(
            DefaultPermissions(allow_non_admins_manage_ssh_fleets=False)
        ):
            response = client.post(
                f"/api/project/{project.name}/fleets/delete",
                headers=get_auth_headers(user.token),
                json={"names": [fleet.name]},
            )
        assert response.status_code in [401, 403]


class TestDeleteFleetInstances:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/fleets/delete_instances")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_terminates_fleet_instances(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        pool = await create_pool(session=session, project=project)
        fleet = await create_fleet(session=session, project=project)
        instance1 = await create_instance(
            session=session,
            project=project,
            pool=pool,
            instance_num=1,
        )
        instance2 = await create_instance(
            session=session,
            project=project,
            pool=pool,
            instance_num=2,
        )
        fleet.instances.append(instance1)
        fleet.instances.append(instance2)
        await session.commit()
        response = client.post(
            f"/api/project/{project.name}/fleets/delete_instances",
            headers=get_auth_headers(user.token),
            json={"name": fleet.name, "instance_nums": [1]},
        )
        assert response.status_code == 200
        await session.refresh(fleet)
        await session.refresh(instance1)
        await session.refresh(instance2)

        assert instance1.status == InstanceStatus.TERMINATING
        assert instance2.status != InstanceStatus.TERMINATING
        assert fleet.status != FleetStatus.TERMINATING

    @pytest.mark.asyncio
    async def test_returns_400_when_deleting_busy_instances(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        pool = await create_pool(session=session, project=project)
        fleet = await create_fleet(session=session, project=project)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
        )
        instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            instance_num=1,
            status=InstanceStatus.BUSY,
            job=job,
        )
        fleet.instances.append(instance)
        await session.commit()
        response = client.post(
            f"/api/project/{project.name}/fleets/delete_instances",
            headers=get_auth_headers(user.token),
            json={"name": fleet.name, "instance_nums": [1]},
        )
        assert response.status_code == 400
        await session.refresh(fleet)
        await session.refresh(instance)

        assert instance.status != InstanceStatus.TERMINATING
        assert fleet.status != FleetStatus.TERMINATING
