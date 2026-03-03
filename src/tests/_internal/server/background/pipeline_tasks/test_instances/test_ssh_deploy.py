import datetime as dt
from typing import Optional
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import SSHProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.server.background.pipeline_tasks.instances import InstanceWorker
from dstack._internal.server.background.pipeline_tasks.instances import (
    ssh_deploy as instances_ssh_deploy,
)
from dstack._internal.server.testing.common import (
    create_instance,
    create_project,
    get_job_provisioning_data,
    get_remote_connection_info,
)
from dstack._internal.utils.common import get_current_datetime
from tests._internal.server.background.pipeline_tasks.test_instances.helpers import (
    process_instance,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestSSHDeploy:
    async def test_pending_ssh_instance_terminates_on_provision_timeout(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime() - dt.timedelta(days=100),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.PROVISIONING_TIMEOUT

    @pytest.mark.parametrize(
        ["cpus", "gpus", "requested_blocks", "expected_blocks"],
        [
            pytest.param(32, 8, 1, 1, id="gpu-instance-no-blocks"),
            pytest.param(32, 8, 2, 2, id="gpu-instance-four-gpu-per-block"),
            pytest.param(32, 8, 4, 4, id="gpu-instance-two-gpus-per-block"),
            pytest.param(32, 8, None, 8, id="gpu-instance-auto-max-gpu"),
            pytest.param(4, 8, None, 4, id="gpu-instance-auto-max-cpu"),
            pytest.param(8, 8, None, 8, id="gpu-instance-auto-max-cpu-and-gpu"),
            pytest.param(32, 0, 1, 1, id="cpu-instance-no-blocks"),
            pytest.param(32, 0, 2, 2, id="cpu-instance-four-cpu-per-block"),
            pytest.param(32, 0, 4, 4, id="cpu-instance-two-cpus-per-block"),
            pytest.param(32, 0, None, 32, id="cpu-instance-auto-max-cpu"),
        ],
    )
    async def test_adds_ssh_instance(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        host_info: dict,
        deploy_instance_mock: Mock,
        cpus: int,
        gpus: int,
        requested_blocks: Optional[int],
        expected_blocks: int,
    ):
        host_info["cpus"] = cpus
        host_info["gpu_count"] = gpus
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
            total_blocks=requested_blocks,
            busy_blocks=0,
        )
        await session.commit()

        await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.IDLE
        assert instance.total_blocks == expected_blocks
        assert instance.busy_blocks == 0
        deploy_instance_mock.assert_called_once()

    async def test_retries_ssh_instance_if_provisioning_fails(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        deploy_instance_mock: Mock,
    ):
        deploy_instance_mock.side_effect = SSHProvisioningError("Expected")
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PENDING
        assert instance.termination_reason is None

    async def test_terminates_ssh_instance_if_deploy_fails_unexpectedly(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        deploy_instance_mock: Mock,
    ):
        deploy_instance_mock.side_effect = RuntimeError("Unexpected")
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert instance.termination_reason_message == "Unexpected error when adding SSH instance"

    async def test_terminates_ssh_instance_if_key_is_invalid(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            instances_ssh_deploy,
            "ssh_keys_to_pkeys",
            Mock(side_effect=ValueError("Bad key")),
        )
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert instance.termination_reason_message == "Unsupported private SSH key type"

    async def test_terminates_ssh_instance_if_internal_ip_cannot_be_resolved_from_network(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        host_info: dict,
        deploy_instance_mock: Mock,
    ):
        host_info["addresses"] = ["192.168.100.100/24"]
        project = await create_project(session=session)
        job_provisioning_data = get_job_provisioning_data(
            dockerized=True,
            backend=BackendType.REMOTE,
            internal_ip=None,
        )
        job_provisioning_data.instance_network = "10.0.0.0/24"
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
            job_provisioning_data=job_provisioning_data,
        )
        await session.commit()

        await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert (
            instance.termination_reason_message
            == "Failed to locate internal IP address on the given network"
        )

    async def test_terminates_ssh_instance_if_internal_ip_is_not_in_host_interfaces(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        host_info: dict,
        deploy_instance_mock: Mock,
    ):
        host_info["addresses"] = ["192.168.100.100/24"]
        project = await create_project(session=session)
        job_provisioning_data = get_job_provisioning_data(
            dockerized=True,
            backend=BackendType.REMOTE,
            internal_ip="10.0.0.20",
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
            job_provisioning_data=job_provisioning_data,
        )
        await session.commit()

        await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert (
            instance.termination_reason_message
            == "Specified internal IP not found among instance interfaces"
        )
