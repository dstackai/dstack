import asyncio
import uuid
from datetime import timedelta
from typing import Optional, Union
from unittest.mock import Mock

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.fleets import (
    ApplyFleetPlanInput,
    FleetConfiguration,
    FleetNodesSpec,
    FleetSpec,
    InstanceGroupPlacement,
    SSHHostParams,
    SSHParams,
    SSHProxyParams,
)
from dstack._internal.core.models.instances import (
    InstanceStatus,
    RemoteConnectionInfo,
    SSHConnectionParams,
    SSHKey,
)
from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.server.background.pipeline_tasks.base import Heartbeater
from dstack._internal.server.background.pipeline_tasks.instances import InstanceFetcher
from dstack._internal.server.models import FleetModel, InstanceModel, ProjectModel
from dstack._internal.server.services.fleets import (
    _check_can_update_ssh_config,
    apply_plan,
    get_fleet_master_instance_provisioning_data,
    get_plan,
)
from dstack._internal.server.services.instances import get_instance_remote_connection_info
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_fleet_spec,
    get_job_provisioning_data,
    get_ssh_key,
    mock_lease,
)
from dstack._internal.utils.common import get_current_datetime
from tests._internal.utils.test_ssh import PRIVATE_KEY, PUBLIC_KEY


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestApplySSHFleetKeys:
    @pytest.mark.parametrize(
        "per_host,busy,rotation",
        [(False, False, "host"), (False, True, "jump"), (True, True, "both")],
    )
    async def test_updates_existing_instances_without_reprovisioning(
        self, test_db, session, monkeypatch, per_host, busy, rotation
    ):
        monkeypatch.setattr(
            "dstack._internal.server.services.backends.cache.lease_project_backends",
            mock_lease([]),
        )
        user = await create_user(session)
        project = await create_project(session, owner=user)
        old_key, new_key = get_ssh_key(), SSHKey(public=PUBLIC_KEY, private=PRIVATE_KEY)
        jump = SSHProxyParams(hostname="jump", user="ubuntu", identity_file="key", ssh_key=old_key)
        ssh_config = SSHParams(
            user="ubuntu",
            identity_file="key",
            ssh_key=old_key,
            proxy_jump=jump,
            hosts=[
                SSHHostParams(
                    hostname="host",
                    identity_file="key",
                    ssh_key=old_key,
                    proxy_jump=jump.model_copy(deep=True),
                )
                if per_host
                else "host"
            ],
        )
        spec = get_fleet_spec(conf=FleetConfiguration(name="fleet", ssh_config=ssh_config))
        fleet = await create_fleet(session, project=project, spec=spec)
        instance = await create_instance(
            session,
            project=project,
            fleet=fleet,
            backend=BackendType.REMOTE,
            status=InstanceStatus.BUSY if busy else InstanceStatus.IDLE,
            remote_connection_info=RemoteConnectionInfo(
                host="host",
                port=22,
                ssh_user="ubuntu",
                ssh_keys=[old_key],
                ssh_proxy=SSHConnectionParams(hostname="jump", port=22, username="ubuntu"),
                ssh_proxy_keys=[old_key],
            ),
        )
        job = None
        if busy:
            repo = await create_repo(session, project_id=project.id)
            run = await create_run(
                session, project, repo, user, fleet=fleet, status=RunStatus.RUNNING
            )
            job = await create_job(session, run, instance=instance, status=JobStatus.RUNNING)
        provisioning = instance.job_provisioning_data
        new = spec.model_copy(deep=True)
        keys = new.configuration.ssh_config
        assert keys is not None
        if per_host:
            keys = keys.hosts[0]
            assert isinstance(keys, SSHHostParams)
        if rotation != "jump":
            keys.identity_file = "new-key"
            keys.ssh_key = new_key
        assert keys.proxy_jump is not None
        if rotation != "host":
            keys.proxy_jump.identity_file = "new-key"
            keys.proxy_jump.ssh_key = new_key
        plan = await get_plan(session, project, user, new)
        assert plan.action == ApplyAction.UPDATE
        assert plan.current_resource is not None and plan.effective_spec is not None
        assert plan.current_resource.spec != plan.effective_spec
        assert PRIVATE_KEY not in plan.effective_spec.model_dump_json()
        updated = await apply_plan(
            session,
            user,
            project,
            ApplyFleetPlanInput(spec=new, current_resource=plan.current_resource),
            False,
            Mock(),
        )
        assert updated.id == fleet.id
        await session.refresh(instance)
        rci = get_instance_remote_connection_info(instance)
        assert rci is not None
        assert rci.ssh_keys == [old_key if rotation == "jump" else new_key]
        assert rci.ssh_proxy_keys == [old_key if rotation == "host" else new_key]
        assert instance.job_provisioning_data == provisioning
        assert instance.status == (InstanceStatus.BUSY if busy else InstanceStatus.IDLE)
        if job is not None:
            await session.refresh(job)
            assert job.status == JobStatus.RUNNING
            assert job.submission_num == 0

    @pytest.mark.parametrize("outcome", ["success", "timeout", "cancel", "lost-lease"])
    async def test_waits_for_instance_processing_without_holding_db_connection(
        self, test_db, session, monkeypatch, outcome
    ):
        monkeypatch.setattr(
            "dstack._internal.server.services.backends.cache.lease_project_backends",
            mock_lease([]),
        )
        user = await create_user(session)
        project = await create_project(session, owner=user)
        old_key = get_ssh_key()
        spec = get_fleet_spec(
            conf=FleetConfiguration(
                name="fleet", ssh_config=SSHParams(user="ubuntu", hosts=["host"], ssh_key=old_key)
            )
        )
        fleet = await create_fleet(session, project=project, spec=spec)
        instance = await create_instance(
            session,
            project=project,
            fleet=fleet,
            backend=BackendType.REMOTE,
            remote_connection_info=RemoteConnectionInfo(
                host="host", port=22, ssh_user="ubuntu", ssh_keys=[old_key]
            ),
        )
        instance.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
        await session.commit()
        new = spec.model_copy(deep=True)
        assert new.configuration.ssh_config is not None
        new.configuration.ssh_config.identity_file = "new-key"
        new.configuration.ssh_config.ssh_key = SSHKey(public=PUBLIC_KEY, private=PRIVATE_KEY)
        plan = await get_plan(session, project, user, new)
        fleet_id, instance_id = fleet.id, instance.id
        original_sleep = asyncio.sleep
        waited = False
        replacement_token = None

        async def finish_processing(delay):
            nonlocal waited, replacement_token
            if delay != 0.1:
                return await original_sleep(0)
            waited = True
            if hasattr(test_db.engine.pool, "checkedout"):
                assert test_db.engine.pool.checkedout() == 0
            # Exercise the actual fetcher while apply owns the fleet lease.
            fetcher = InstanceFetcher(
                queue=asyncio.Queue(),
                queue_desired_minsize=1,
                min_processing_interval=timedelta(seconds=7),
                lock_timeout=timedelta(seconds=30),
                heartbeater=Heartbeater(
                    model_type=InstanceModel,
                    lock_timeout=timedelta(seconds=30),
                    heartbeat_trigger=timedelta(seconds=15),
                ),
            )
            assert await fetcher.fetch(1) == []
            if outcome == "cancel":
                raise asyncio.CancelledError
            async with test_db.get_session() as processing:
                if outcome == "lost-lease":
                    replacement_token = uuid.uuid4()
                    await processing.execute(
                        update(FleetModel)
                        .where(FleetModel.id == fleet_id)
                        .values(lock_token=replacement_token)
                    )
                else:
                    await processing.execute(
                        update(InstanceModel)
                        .where(InstanceModel.id == instance_id)
                        .values(lock_expires_at=None)
                    )
                await processing.commit()

        monkeypatch.setattr(asyncio, "sleep", finish_processing)
        if outcome == "timeout":
            monkeypatch.setattr(
                "dstack._internal.server.services.fleets._SSH_KEY_UPDATE_WAIT_SECONDS", 0
            )
        request = ApplyFleetPlanInput(spec=new, current_resource=plan.current_resource)
        if outcome == "success":
            await apply_plan(session, user, project, request, False, Mock())
        elif outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await apply_plan(session, user, project, request, False, Mock())
        else:
            with pytest.raises(
                ServerClientError, match="Timed out" if outcome == "timeout" else "lock was lost"
            ):
                await apply_plan(session, user, project, request, False, Mock())
        assert waited == (outcome != "timeout")
        await session.refresh(instance)
        await session.refresh(fleet)
        expected = (
            SSHKey(public=PUBLIC_KEY, private=PRIVATE_KEY) if outcome == "success" else old_key
        )
        rci = get_instance_remote_connection_info(instance)
        assert rci is not None and rci.ssh_keys == [expected]
        stored = FleetSpec.model_validate_json(fleet.spec).configuration.ssh_config
        assert stored is not None and stored.ssh_key == expected
        if outcome == "lost-lease":
            assert fleet.lock_token == replacement_token
            assert fleet.lock_expires_at is not None
        else:
            assert fleet.lock_token is None
            assert fleet.lock_expires_at is None


class TestCheckCanUpdateSSHConfig:
    @pytest.mark.parametrize(
        "field,value", [("hostname", "other"), ("port", 2222), ("user", "other")]
    )
    @pytest.mark.parametrize("per_host", [False, True])
    def test_rejects_jump_route_changes(self, field, value, per_host):
        jump = SSHProxyParams(hostname="jump", user="ubuntu", identity_file="key")
        current = SSHParams(
            hosts=[SSHHostParams(hostname="host", proxy_jump=jump)] if per_host else ["host"],
            proxy_jump=None if per_host else jump,
        )
        new = current.model_copy(deep=True)
        if per_host:
            host = new.hosts[0]
            assert isinstance(host, SSHHostParams)
            target = host.proxy_jump
        else:
            target = new.proxy_jump
        assert target is not None
        setattr(target, field, value)
        with pytest.raises(ServerClientError):
            _check_can_update_ssh_config(current, new)


class TestGetPlanSSHFleetHostsValidation:
    @pytest.fixture
    def lease_project_backends_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = mock_lease([])
        monkeypatch.setattr(
            "dstack._internal.server.services.backends.cache.lease_project_backends", mock
        )
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
    @pytest.mark.usefixtures("test_db", "lease_project_backends_mock")
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
    @pytest.mark.usefixtures("test_db", "lease_project_backends_mock")
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
    @pytest.mark.usefixtures("test_db", "lease_project_backends_mock")
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
    @pytest.mark.usefixtures("test_db", "lease_project_backends_mock")
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
    @pytest.mark.usefixtures("test_db", "lease_project_backends_mock")
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
    @pytest.mark.usefixtures("test_db", "lease_project_backends_mock")
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


class TestGetFleetMasterInstanceProvisioningData:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_none_without_current_master_instance(
        self, test_db, session: AsyncSession
    ) -> None:
        project = await create_project(session=session)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=1, max=2)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            job_provisioning_data=get_job_provisioning_data(region="eu-west-1"),
        )

        master_provisioning_data = get_fleet_master_instance_provisioning_data(
            fleet_model=fleet,
            fleet_spec=fleet_spec,
        )

        assert master_provisioning_data is None
