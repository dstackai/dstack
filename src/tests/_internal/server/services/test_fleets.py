from typing import Optional, Union
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import (
    FleetConfiguration,
    FleetSpec,
    SSHHostParams,
    SSHParams,
)
from dstack._internal.core.models.instances import RemoteConnectionInfo
from dstack._internal.server.models import FleetModel, ProjectModel
from dstack._internal.server.services.backends import get_project_backends
from dstack._internal.server.services.fleets import get_plan
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_project,
    create_user,
    get_fleet_spec,
    get_ssh_key,
)


class TestGetPlanSSHFleetHostsValidation:
    @pytest.fixture
    def get_project_backends_mock(self, monkeypatch: pytest.MonkeyPatch) -> list[Backend]:
        mock = Mock(spec_set=get_project_backends, return_value=[])
        monkeypatch.setattr("dstack._internal.server.services.backends.get_project_backends", mock)
        return mock

    def get_ssh_fleet_spec(
        self, name: Optional[str], hosts: list[Union[SSHHostParams, str]]
    ) -> FleetSpec:
        ssh_config = SSHParams(
            hosts=hosts,
            network=None,
            user="ubuntu",
            ssh_key=get_ssh_key(),
        )
        fleet_conf = FleetConfiguration(name=name, ssh_config=ssh_config)
        return get_fleet_spec(conf=fleet_conf)

    async def create_fleet(
        self, session: AsyncSession, project: ProjectModel, spec: FleetSpec
    ) -> FleetModel:
        assert spec.configuration.ssh_config is not None, spec.configuration
        fleet = await create_fleet(session=session, project=project, spec=spec)
        for host in spec.configuration.ssh_config.hosts:
            if isinstance(host, SSHHostParams):
                hostname = host.hostname
            else:
                hostname = host
            rci = RemoteConnectionInfo(host=hostname, port=22, ssh_user="admin", ssh_keys=[])
            await create_instance(
                session=session,
                project=project,
                fleet=fleet,
                backend=BackendType.REMOTE,
                remote_connection_info=rci,
            )
        return fleet

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.usefixtures("test_db", "get_project_backends_mock")
    async def test_ok_same_fleet_update(self, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        old_fleet_spec = self.get_ssh_fleet_spec(name="my-fleet", hosts=["192.168.100.201"])
        await self.create_fleet(session, project, old_fleet_spec)
        new_fleet_spec = self.get_ssh_fleet_spec(
            name="my-fleet", hosts=["192.168.100.201", "192.168.100.202"]
        )
        plan = await get_plan(session=session, project=project, user=user, spec=new_fleet_spec)
        assert plan.current_resource is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.usefixtures("test_db", "get_project_backends_mock")
    async def test_ok_deleted_instances_ignored(self, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        deleted_fleet_spec = self.get_ssh_fleet_spec(name="my-fleet", hosts=["192.168.100.201"])
        deleted_fleet = await self.create_fleet(session, project, deleted_fleet_spec)
        for instance in deleted_fleet.instances:
            instance.deleted = True
        deleted_fleet.deleted = True
        await session.commit()
        fleet_spec = self.get_ssh_fleet_spec(
            name="my-fleet", hosts=["192.168.100.201", "192.168.100.202"]
        )
        plan = await get_plan(session=session, project=project, user=user, spec=fleet_spec)
        assert plan.current_resource is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.usefixtures("test_db", "get_project_backends_mock")
    async def test_ok_no_common_hosts_with_another_fleet(self, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        another_fleet_spec = self.get_ssh_fleet_spec(
            name="another-fleet", hosts=["192.168.100.201"]
        )
        await self.create_fleet(session, project, another_fleet_spec)
        fleet_spec = self.get_ssh_fleet_spec(name="new-fleet", hosts=["192.168.100.202"])
        plan = await get_plan(session=session, project=project, user=user, spec=fleet_spec)
        assert plan.current_resource is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.usefixtures("test_db", "get_project_backends_mock")
    async def test_error_another_fleet_same_project(self, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        another_fleet_spec = self.get_ssh_fleet_spec(
            name="another-fleet", hosts=["192.168.100.201"]
        )
        await self.create_fleet(session, project, another_fleet_spec)
        fleet_spec = self.get_ssh_fleet_spec(
            name="new-fleet", hosts=["192.168.100.201", "192.168.100.202"]
        )
        with pytest.raises(
            ServerClientError, match=r"Instances \[192\.168\.100\.201\] are already assigned"
        ):
            await get_plan(session=session, project=project, user=user, spec=fleet_spec)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.usefixtures("test_db", "get_project_backends_mock")
    async def test_error_another_fleet_another_project(self, session: AsyncSession):
        another_user = await create_user(session=session, name="another-user")
        another_project = await create_project(
            session=session, owner=another_user, name="another-project"
        )
        another_fleet_spec = self.get_ssh_fleet_spec(
            name="another-fleet", hosts=["192.168.100.201"]
        )
        await self.create_fleet(session, another_project, another_fleet_spec)
        user = await create_user(session=session, name="my-user")
        project = await create_project(session=session, owner=user, name="my-project")
        fleet_spec = self.get_ssh_fleet_spec(
            name="my-fleet", hosts=["192.168.100.201", "192.168.100.202"]
        )
        with pytest.raises(
            ServerClientError, match=r"Instances \[192\.168\.100\.201\] are already assigned"
        ):
            await get_plan(session=session, project=project, user=user, spec=fleet_spec)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.usefixtures("test_db", "get_project_backends_mock")
    async def test_error_fleet_spec_without_name(self, session: AsyncSession):
        # Even if the user apply the same configuration again, we cannot be sure if it is the same
        # fleet or a brand new fleet, as we identify fleets by name.
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        existing_fleet_spec = self.get_ssh_fleet_spec(
            name="autogenerated-fleet-name", hosts=["192.168.100.201"]
        )
        await self.create_fleet(session, project, existing_fleet_spec)
        fleet_spec_without_name = self.get_ssh_fleet_spec(name=None, hosts=["192.168.100.201"])
        with pytest.raises(
            ServerClientError, match=r"Instances \[192\.168\.100\.201\] are already assigned"
        ):
            await get_plan(
                session=session, project=project, user=user, spec=fleet_spec_without_name
            )
