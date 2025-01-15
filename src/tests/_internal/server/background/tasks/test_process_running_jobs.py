from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import (
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
)
from dstack._internal.core.models.volumes import (
    InstanceMountPoint,
    VolumeMountPoint,
    VolumeStatus,
)
from dstack._internal.server import settings
from dstack._internal.server.background.tasks.process_running_jobs import process_running_jobs
from dstack._internal.server.schemas.runner import (
    HealthcheckResponse,
    JobStateEvent,
    PortMapping,
    PullResponse,
    TaskStatus,
)
from dstack._internal.server.services.runner.client import RunnerClient, ShimClient
from dstack._internal.server.services.runner.ssh import SSHTunnel
from dstack._internal.server.services.volumes import (
    volume_model_to_volume,
)
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_pool,
    create_project,
    create_repo,
    create_run,
    create_user,
    create_volume,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_run_spec,
    get_volume_configuration,
)
from dstack._internal.utils.common import get_current_datetime

pytestmark = pytest.mark.usefixtures("image_config_mock")


@pytest.fixture
def ssh_tunnel_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = MagicMock(spec_set=SSHTunnel)
    monkeypatch.setattr("dstack._internal.server.services.runner.ssh.SSHTunnel", mock)
    return mock


@pytest.fixture
def shim_client_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock(spec_set=ShimClient)
    mock.healthcheck.return_value = HealthcheckResponse(service="dstack-shim", version="latest")
    monkeypatch.setattr(
        "dstack._internal.server.services.runner.client.ShimClient", Mock(return_value=mock)
    )

    return mock


@pytest.fixture
def runner_client_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock(spec_set=RunnerClient)
    mock.healthcheck.return_value = HealthcheckResponse(
        service="dstack-runner", version="0.0.1.dev2"
    )
    monkeypatch.setattr(
        "dstack._internal.server.services.runner.client.RunnerClient", Mock(return_value=mock)
    )
    return mock


class TestProcessRunningJobs:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_leaves_provisioning_job_unchanged_if_runner_not_alive(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
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
        job_provisioning_data = get_job_provisioning_data(dockerized=False)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=datetime(2023, 1, 2, 5, 12, 30, 5, tzinfo=timezone.utc),
            job_provisioning_data=job_provisioning_data,
        )
        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as RunnerClientMock,
            patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock,
        ):
            datetime_mock.return_value = datetime(2023, 1, 2, 5, 12, 30, 10, tzinfo=timezone.utc)
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.healthcheck = Mock()
            runner_client_mock.healthcheck.return_value = None
            await process_running_jobs()
            SSHTunnelMock.assert_called_once()
            runner_client_mock.healthcheck.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_runs_provisioning_job(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
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
        job_provisioning_data = get_job_provisioning_data(dockerized=False)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            job_provisioning_data=job_provisioning_data,
        )
        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as RunnerClientMock,
        ):
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.healthcheck.return_value = HealthcheckResponse(
                service="dstack-runner", version="0.0.1.dev2"
            )
            await process_running_jobs()
            SSHTunnelMock.assert_called_once()
            runner_client_mock.healthcheck.assert_called_once()
            runner_client_mock.submit_job.assert_called_once()
            runner_client_mock.upload_code.assert_called_once()
            runner_client_mock.run_job.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.RUNNING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_updates_running_job(self, test_db, session: AsyncSession, tmp_path: Path):
        project = await create_project(session=session)
        user = await create_user(session=session)
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
        job_provisioning_data = get_job_provisioning_data(dockerized=False)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=job_provisioning_data,
        )
        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as RunnerClientMock,
            patch.object(settings, "SERVER_DIR_PATH", tmp_path),
        ):
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[JobStateEvent(timestamp=1, state=JobStatus.RUNNING)],
                job_logs=[],
                runner_logs=[],
                last_updated=1,
            )
            await process_running_jobs()
            SSHTunnelMock.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert job.runner_timestamp == 1
        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as RunnerClientMock,
        ):
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[JobStateEvent(timestamp=1, state=JobStatus.DONE)],
                job_logs=[],
                runner_logs=[],
                last_updated=2,
            )
            await process_running_jobs()
            SSHTunnelMock.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.DONE_BY_RUNNER
        assert job.runner_timestamp == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("privileged", [False, True])
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisioning_shim_with_volumes(
        self,
        test_db,
        session: AsyncSession,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        privileged: bool,
    ):
        project_ssh_pub_key = "__project_ssh_pub_key__"
        project = await create_project(session=session, ssh_public_key=project_ssh_pub_key)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            configuration=get_volume_configuration(
                name="my-vol", backend=BackendType.AWS, region="us-east-1"
            ),
            backend=BackendType.AWS,
            region="us-east-1",
        )
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.privileged = privileged
        run_spec.configuration.volumes = [
            VolumeMountPoint(name="my-vol", path="/volume"),
            InstanceMountPoint(instance_path="/root/.cache", path="/cache"),
        ]
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )
        job_provisioning_data = get_job_provisioning_data(dockerized=True)

        with patch(
            "dstack._internal.server.services.jobs.configurators.base.get_default_python_verison"
        ) as PyVersion:
            PyVersion.return_value = "3.13"
            job = await create_job(
                session=session,
                run=run,
                status=JobStatus.PROVISIONING,
                job_provisioning_data=job_provisioning_data,
            )

        await process_running_jobs()

        ssh_tunnel_mock.assert_called_once()
        shim_client_mock.healthcheck.assert_called_once()
        shim_client_mock.submit_task.assert_called_once_with(
            task_id=job.id,
            name="test-run-0-0",
            registry_username="",
            registry_password="",
            image_name="dstackai/base:py3.13-0.6-cuda-12.1",
            container_user="root",
            privileged=privileged,
            gpu=None,
            cpu=None,
            memory=None,
            shm_size=None,
            network_mode=NetworkMode.HOST,
            volumes=[volume_model_to_volume(volume)],
            volume_mounts=[VolumeMountPoint(name="my-vol", path="/volume")],
            instance_mounts=[InstanceMountPoint(instance_path="/root/.cache", path="/cache")],
            host_ssh_user="ubuntu",
            host_ssh_keys=["user_ssh_key"],
            container_ssh_keys=[project_ssh_pub_key, "user_ssh_key"],
        )
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PULLING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_pulling_shim(
        self,
        test_db,
        session: AsyncSession,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            job_runtime_data=get_job_runtime_data(network_mode="bridge", ports=None),
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING
        shim_client_mock.get_task.return_value.ports = [
            PortMapping(container=10022, host=32771),
            PortMapping(container=10999, host=32772),
        ]

        await process_running_jobs()

        assert ssh_tunnel_mock.call_count == 2
        shim_client_mock.get_task.assert_called_once()
        runner_client_mock.healthcheck.assert_called_once()
        runner_client_mock.submit_job.assert_called_once()
        runner_client_mock.upload_code.assert_called_once()
        runner_client_mock.run_job.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert JobRuntimeData.__response__.parse_raw(job.job_runtime_data).ports == {
            10022: 32771,
            10999: 32772,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_pulling_shim_port_mapping_not_ready(
        self,
        test_db,
        session: AsyncSession,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job_provisioning_data = get_job_provisioning_data(dockerized=True)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=job_provisioning_data,
            job_runtime_data=get_job_runtime_data(network_mode="bridge", ports=None),
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING
        shim_client_mock.get_task.return_value.ports = None

        await process_running_jobs()

        ssh_tunnel_mock.assert_called_once()
        shim_client_mock.get_task.assert_called_once()
        runner_client_mock.healthcheck.assert_not_called()
        runner_client_mock.submit_job.assert_not_called()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PULLING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_pulling_shim_failed(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
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
        pool = await create_pool(session, project)
        instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            status=InstanceStatus.IDLE,
        )
        job_provisioning_data = get_job_provisioning_data(dockerized=True)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=job_provisioning_data,
            instance=instance,
        )
        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock,
            patch("dstack._internal.server.services.runner.ssh.time.sleep"),
        ):
            SSHTunnelMock.side_effect = SSHError
            await process_running_jobs()
            assert SSHTunnelMock.call_count == 3
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
        assert job.remove_at is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisioning_shim_force_stop_if_already_running_api_v1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        test_db,
        session: AsyncSession,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.image = "debian"
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            submitted_at=get_current_datetime(),
        )
        monkeypatch.setattr(
            "dstack._internal.server.services.runner.ssh.SSHTunnel", Mock(return_value=MagicMock())
        )
        shim_client_mock = Mock()
        monkeypatch.setattr(
            "dstack._internal.server.services.runner.client.ShimClient",
            Mock(return_value=shim_client_mock),
        )
        shim_client_mock.healthcheck.return_value = HealthcheckResponse(
            service="dstack-shim", version="0.0.1.dev2"
        )
        shim_client_mock.is_api_v2_supported.return_value = False
        shim_client_mock.submit.return_value = False

        await process_running_jobs()

        shim_client_mock.healthcheck.assert_called_once()
        shim_client_mock.submit.assert_called_once()
        shim_client_mock.stop.assert_called_once_with(force=True)
        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING
