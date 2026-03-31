import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal import settings
from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.configurations import (
    DevEnvironmentConfiguration,
    ProbeConfig,
    ServiceConfiguration,
)
from dstack._internal.core.models.gateways import GatewayStatus
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import StartupOrder, UtilizationPolicy
from dstack._internal.core.models.runs import (
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
    RunStatus,
)
from dstack._internal.core.models.volumes import InstanceMountPoint, VolumeMountPoint, VolumeStatus
from dstack._internal.server import settings as server_settings
from dstack._internal.server.background.pipeline_tasks.jobs_running import (
    JobRunningFetcher,
    JobRunningPipeline,
    JobRunningPipelineItem,
    JobRunningWorker,
    _RunnerAvailability,
    _SubmitJobToRunnerResult,
)
from dstack._internal.server.background.pipeline_tasks.runs import RunPipeline
from dstack._internal.server.models import JobModel, ProbeModel
from dstack._internal.server.schemas.runner import (
    HealthcheckResponse,
    JobInfoResponse,
    JobStateEvent,
    PortMapping,
    PullResponse,
    TaskStatus,
)
from dstack._internal.server.services.runner.client import RunnerClient, ShimClient
from dstack._internal.server.services.runner.ssh import SSHTunnel
from dstack._internal.server.services.volumes import volume_model_to_volume
from dstack._internal.server.testing.common import (
    create_backend,
    create_export,
    create_fleet,
    create_gateway,
    create_gateway_compute,
    create_instance,
    create_job,
    create_job_metrics_point,
    create_probe,
    create_project,
    create_repo,
    create_run,
    create_user,
    create_volume,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_run_spec,
    get_volume_configuration,
    list_events,
)
from dstack._internal.utils.common import get_current_datetime

pytestmark = pytest.mark.usefixtures("image_config_mock")


@dataclass
class _ProbeSetup:
    success_streak: int
    ready_after: int


@pytest.fixture
def fetcher() -> JobRunningFetcher:
    return JobRunningFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=10),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


@pytest.fixture
def worker() -> JobRunningWorker:
    return JobRunningWorker(queue=Mock(), heartbeater=Mock())


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


def _lock_job_foreign(job_model) -> None:
    job_model.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = "OtherPipeline"


def _lock_job_expired_same_owner(job_model) -> None:
    job_model.lock_expires_at = get_current_datetime() - timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = JobRunningPipeline.__name__


def _lock_job(job_model) -> None:
    job_model.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = JobRunningPipeline.__name__


def _job_to_pipeline_item(job_model) -> JobRunningPipelineItem:
    assert job_model.lock_token is not None
    assert job_model.lock_expires_at is not None
    return JobRunningPipelineItem(
        __tablename__=job_model.__tablename__,
        id=job_model.id,
        lock_token=job_model.lock_token,
        lock_expires_at=job_model.lock_expires_at,
        prev_lock_expired=False,
        status=job_model.status,
        replica_num=job_model.replica_num,
    )


async def _process_job(
    session: AsyncSession,
    worker: JobRunningWorker,
    job_model,
) -> None:
    _lock_job(job_model)
    await session.commit()
    await worker.process(_job_to_pipeline_item(job_model))


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestJobRunningFetcher:
    async def test_fetch_selects_eligible_jobs_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        provisioning = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            last_processed_at=stale - timedelta(seconds=4),
        )
        pulling = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            last_processed_at=stale - timedelta(seconds=3),
        )
        running = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=2),
        )
        expired_same_owner = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=1),
        )
        _lock_job_expired_same_owner(expired_same_owner)

        recent = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=now,
        )
        foreign_locked = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale,
        )
        _lock_job_foreign(foreign_locked)
        finished = await create_job(
            session=session,
            run=run,
            status=JobStatus.DONE,
            last_processed_at=stale - timedelta(seconds=5),
        )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [
            provisioning.id,
            pulling.id,
            running.id,
            expired_same_owner.id,
        ]
        assert [item.status for item in items] == [
            JobStatus.PROVISIONING,
            JobStatus.PULLING,
            JobStatus.RUNNING,
            JobStatus.RUNNING,
        ]

        for job in [
            provisioning,
            pulling,
            running,
            expired_same_owner,
            recent,
            foreign_locked,
            finished,
        ]:
            await session.refresh(job)

        fetched_jobs = [provisioning, pulling, running, expired_same_owner]
        assert all(job.lock_owner == JobRunningPipeline.__name__ for job in fetched_jobs)
        assert all(job.lock_expires_at is not None for job in fetched_jobs)
        assert all(job.lock_token is not None for job in fetched_jobs)
        assert len({job.lock_token for job in fetched_jobs}) == 1

        assert recent.lock_owner is None
        assert foreign_locked.lock_owner == "OtherPipeline"
        assert finished.lock_owner is None

    async def test_fetch_excludes_jobs_from_terminating_runs(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        active_run = await create_run(session=session, project=project, repo=repo, user=user)
        terminating_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="terminating-run",
            status=RunStatus.TERMINATING,
        )
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        active_job = await create_job(
            session=session,
            run=active_run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=1),
        )
        terminating_run_job = await create_job(
            session=session,
            run=terminating_run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=2),
        )

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [active_job.id]

        await session.refresh(active_job)
        await session.refresh(terminating_run_job)

        assert active_job.lock_owner == JobRunningPipeline.__name__
        assert terminating_run_job.lock_owner is None

    async def test_fetch_allows_stale_job_locks_even_if_run_is_waiting_for_job_locks(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        stale = get_current_datetime() - timedelta(minutes=1)

        run.lock_owner = RunPipeline.__name__
        run.lock_token = None
        run.lock_expires_at = None

        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=1),
        )
        _lock_job_expired_same_owner(job)
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [job.id]

        await session.refresh(job)
        assert job.lock_owner == JobRunningPipeline.__name__

    async def test_fetch_excludes_jobs_when_run_is_waiting_for_related_job_locks(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        stale = get_current_datetime() - timedelta(minutes=1)

        run.lock_owner = RunPipeline.__name__
        run.lock_token = None
        run.lock_expires_at = None

        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=1),
        )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert items == []

        await session.refresh(job)
        assert job.lock_owner is None

    async def test_fetch_returns_oldest_jobs_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()

        oldest = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == JobRunningPipeline.__name__
        assert middle.lock_owner == JobRunningPipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestJobRunningWorker:
    async def test_process_skips_when_lock_token_changes(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=False),
            instance=instance,
            instance_assigned=True,
        )
        _lock_job(job)
        await session.commit()

        item = _job_to_pipeline_item(job)
        new_lock_token = uuid.uuid4()
        job.lock_token = new_lock_token
        await session.commit()

        await worker.process(item)
        await session.refresh(job)

        assert job.lock_token == new_lock_token
        assert job.status == JobStatus.PROVISIONING
        assert job.lock_owner == JobRunningPipeline.__name__

    async def test_leaves_provisioning_job_unchanged_if_runner_not_alive(
        self, test_db, session: AsyncSession, worker: JobRunningWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=False),
            instance=instance,
            instance_assigned=True,
        )

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as runner_client_cls,
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_file_archives",
                new_callable=AsyncMock,
            ) as get_job_file_archives_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_code",
                new_callable=AsyncMock,
            ) as get_job_code_mock,
        ):
            runner_client_mock = runner_client_cls.return_value
            runner_client_mock.healthcheck.return_value = None
            await _process_job(session, worker, job)
            ssh_tunnel_cls.assert_called_once()
            runner_client_mock.healthcheck.assert_called_once()
            get_job_file_archives_mock.assert_not_awaited()
            get_job_code_mock.assert_not_awaited()

        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING
        assert job.lock_token is None
        assert job.lock_owner is None

    async def test_runs_provisioning_job(
        self, test_db, session: AsyncSession, worker: JobRunningWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=False),
            job_runtime_data=get_job_runtime_data(),
            instance=instance,
            instance_assigned=True,
        )
        before_processed_at = job.last_processed_at

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as runner_client_cls,
        ):
            runner_client_mock = runner_client_cls.return_value
            runner_client_mock.healthcheck.return_value = HealthcheckResponse(
                service="dstack-runner", version="0.0.1.dev2"
            )
            runner_client_mock.run_job.return_value = JobInfoResponse(
                working_dir="/dstack/run", username="dstack"
            )
            await _process_job(session, worker, job)
            assert ssh_tunnel_cls.call_count == 2
            assert runner_client_mock.healthcheck.call_count == 2
            runner_client_mock.submit_job.assert_called_once()
            runner_client_mock.upload_code.assert_called_once()
            runner_client_mock.run_job.assert_called_once()

        await session.refresh(job)
        assert job.status == JobStatus.RUNNING
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner is None
        assert job.last_processed_at > before_processed_at
        job_runtime_data = JobRuntimeData.__response__.parse_raw(job.job_runtime_data)
        assert job_runtime_data.working_dir == "/dstack/run"
        assert job_runtime_data.username == "dstack"

    @pytest.mark.parametrize("privileged", [False, True])
    async def test_provisioning_shim_with_volumes(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        privileged: bool,
    ):
        project_ssh_pub_key = "__project_ssh_pub_key__"
        project = await create_project(session=session, ssh_public_key=project_ssh_pub_key)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
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
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job_provisioning_data = get_job_provisioning_data(dockerized=True)

        with patch(
            "dstack._internal.server.services.jobs.configurators.base.get_default_python_verison"
        ) as py_version:
            py_version.return_value = "3.13"
            job = await create_job(
                session=session,
                run=run,
                status=JobStatus.PROVISIONING,
                submitted_at=get_current_datetime(),
                job_provisioning_data=job_provisioning_data,
                instance=instance,
                instance_assigned=True,
            )

        await _process_job(session, worker, job)

        ssh_tunnel_mock.assert_called_once()
        shim_client_mock.healthcheck.assert_called_once()
        shim_client_mock.submit_task.assert_called_once_with(
            task_id=job.id,
            name="test-run-0-0",
            registry_username="",
            registry_password="",
            image_name=(
                f"dstackai/base:{settings.DSTACK_BASE_IMAGE_VERSION}-"
                f"base-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
            ),
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
            gpu_devices=[],
            host_ssh_user="ubuntu",
            host_ssh_keys=["user_ssh_key"],
            container_ssh_keys=[project_ssh_pub_key, "user_ssh_key"],
            instance_id=job_provisioning_data.instance_id,
        )
        await session.refresh(job)
        assert job.status == JobStatus.PULLING

    async def test_pulling_shim(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            job_runtime_data=get_job_runtime_data(network_mode="bridge", ports=None),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING
        shim_client_mock.get_task.return_value.ports = [
            PortMapping(container=10022, host=32771),
            PortMapping(container=10999, host=32772),
        ]
        runner_client_mock.run_job.return_value = JobInfoResponse(
            working_dir="/dstack/run", username="dstack"
        )

        await _process_job(session, worker, job)

        assert ssh_tunnel_mock.call_count == 3
        shim_client_mock.get_task.assert_called_once()
        assert runner_client_mock.healthcheck.call_count == 2
        runner_client_mock.submit_job.assert_called_once()
        runner_client_mock.upload_code.assert_called_once()
        runner_client_mock.run_job.assert_called_once()
        await session.refresh(job)
        assert job.status == JobStatus.RUNNING
        job_runtime_data = JobRuntimeData.__response__.parse_raw(job.job_runtime_data)
        assert job_runtime_data.ports == {10022: 32771, 10999: 32772}
        assert job_runtime_data.working_dir == "/dstack/run"
        assert job_runtime_data.username == "dstack"

    async def test_pulling_shim_port_mapping_not_ready(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            job_runtime_data=get_job_runtime_data(network_mode="bridge", ports=None),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING
        shim_client_mock.get_task.return_value.ports = None

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_file_archives",
                new_callable=AsyncMock,
            ) as get_job_file_archives_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_code",
                new_callable=AsyncMock,
            ) as get_job_code_mock,
        ):
            await _process_job(session, worker, job)
            ssh_tunnel_mock.assert_called_once()
            shim_client_mock.get_task.assert_called_once()
            runner_client_mock.healthcheck.assert_not_called()
            runner_client_mock.submit_job.assert_not_called()
            get_job_file_archives_mock.assert_not_awaited()
            get_job_code_mock.assert_not_awaited()

        await session.refresh(job)
        assert job.status == JobStatus.PULLING

    async def test_pulling_shim_waiting_resets_disconnect_and_emits_reachable_event(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            submitted_at=get_current_datetime(),
            disconnected_at=get_current_datetime() - timedelta(minutes=1),
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            job_runtime_data=get_job_runtime_data(network_mode="bridge", ports=None),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING
        shim_client_mock.get_task.return_value.ports = None

        await _process_job(session, worker, job)

        ssh_tunnel_mock.assert_called_once()
        shim_client_mock.get_task.assert_called_once()
        runner_client_mock.healthcheck.assert_not_called()
        await session.refresh(job)
        events = await list_events(session)
        assert job.status == JobStatus.PULLING
        assert job.disconnected_at is None
        assert len(events) == 1
        assert events[0].message == "Job became reachable"

    async def test_pulling_shim_runner_not_ready(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            job_runtime_data=get_job_runtime_data(network_mode="bridge", ports=None),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING
        shim_client_mock.get_task.return_value.ports = [
            PortMapping(container=10022, host=32771),
            PortMapping(container=10999, host=32772),
        ]
        runner_client_mock.healthcheck.return_value = None

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_file_archives",
                new_callable=AsyncMock,
            ) as get_job_file_archives_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_code",
                new_callable=AsyncMock,
            ) as get_job_code_mock,
        ):
            await _process_job(session, worker, job)
            assert ssh_tunnel_mock.call_count == 2
            shim_client_mock.get_task.assert_called_once()
            runner_client_mock.healthcheck.assert_called_once()
            runner_client_mock.submit_job.assert_not_called()
            get_job_file_archives_mock.assert_not_awaited()
            get_job_code_mock.assert_not_awaited()

        await session.refresh(job)
        assert job.status == JobStatus.PULLING

    async def test_pulling_shim_uses_runtime_port_mapping_for_runner_calls(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            job_runtime_data=get_job_runtime_data(network_mode="bridge", ports=None),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING
        shim_client_mock.get_task.return_value.ports = [
            PortMapping(container=10022, host=32771),
            PortMapping(container=10999, host=32772),
        ]
        expected_ports = {10022: 32771, 10999: 32772}

        def assert_runner_availability(_, __, job_runtime_data):
            assert job_runtime_data is not None
            assert job_runtime_data.ports == expected_ports
            return _RunnerAvailability.AVAILABLE

        def assert_submit_job_to_runner(_, __, job_runtime_data, **kwargs):
            assert job_runtime_data is not None
            assert job_runtime_data.ports == expected_ports
            return _SubmitJobToRunnerResult(success=True)

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_runner_availability",
                side_effect=assert_runner_availability,
            ) as get_runner_availability_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._submit_job_to_runner",
                side_effect=assert_submit_job_to_runner,
            ) as submit_job_to_runner_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_file_archives",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_code",
                new_callable=AsyncMock,
                return_value=b"",
            ),
        ):
            await _process_job(session, worker, job)
            ssh_tunnel_mock.assert_called_once()
            get_runner_availability_mock.assert_called_once()
            submit_job_to_runner_mock.assert_called_once()

        await session.refresh(job)
        assert job.status == JobStatus.PULLING
        job_runtime_data = JobRuntimeData.__response__.parse_raw(job.job_runtime_data)
        assert job_runtime_data.ports == expected_ports

    async def test_pulling_shim_failed(
        self, test_db, session: AsyncSession, worker: JobRunningWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.IDLE
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
        )

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch("dstack._internal.server.services.runner.ssh.time.sleep"),
        ):
            from dstack._internal.core.errors import SSHError

            ssh_tunnel_cls.side_effect = SSHError
            await _process_job(session, worker, job)
            assert ssh_tunnel_cls.call_count == 3

        await session.refresh(job)
        events = await list_events(session)
        assert job.disconnected_at is not None
        assert job.status == JobStatus.PULLING
        assert len(events) == 1
        assert events[0].message == "Job became unreachable"

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch("dstack._internal.server.services.runner.ssh.time.sleep"),
            freeze_time(job.disconnected_at + timedelta(minutes=5)),
        ):
            from dstack._internal.core.errors import SSHError

            ssh_tunnel_cls.side_effect = SSHError
            await _process_job(session, worker, job)
            assert ssh_tunnel_cls.call_count == 3

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.INSTANCE_UNREACHABLE
        assert job.remove_at is None

    async def test_provisioning_shim_force_stop_if_already_running_api_v1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
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
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
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

        await _process_job(session, worker, job)

        shim_client_mock.healthcheck.assert_called_once()
        shim_client_mock.submit.assert_called_once()
        shim_client_mock.stop.assert_called_once_with(force=True)
        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING

    async def test_master_job_waits_for_workers(
        self, test_db, session: AsyncSession, worker: JobRunningWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.startup_order = StartupOrder.WORKERS_FIRST
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        instance1 = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        instance2 = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job_provisioning_data = get_job_provisioning_data(dockerized=False)
        master_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=job_provisioning_data,
            instance_assigned=True,
            instance=instance1,
            job_num=0,
            last_processed_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        worker_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=job_provisioning_data,
            instance_assigned=True,
            instance=instance2,
            job_num=1,
            last_processed_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
        )

        await _process_job(session, worker, master_job)
        await session.refresh(master_job)
        assert master_job.status == JobStatus.PROVISIONING

        worker_job.status = JobStatus.RUNNING
        master_job.last_processed_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel"),
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as runner_client_cls,
        ):
            runner_client_mock = runner_client_cls.return_value
            runner_client_mock.healthcheck.return_value = HealthcheckResponse(
                service="dstack-runner", version="0.0.1.dev2"
            )
            await _process_job(session, worker, master_job)

        await session.refresh(master_job)
        assert master_job.status == JobStatus.RUNNING

    async def test_apply_skips_when_lock_token_changes_after_processing(
        self, test_db, session: AsyncSession, worker: JobRunningWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=get_current_datetime(),
            job_provisioning_data=get_job_provisioning_data(dockerized=False),
            job_runtime_data=get_job_runtime_data(),
            instance=instance,
            instance_assigned=True,
        )
        _lock_job(job)
        await session.commit()
        original_lock_token = job.lock_token
        replacement_lock_token = uuid.uuid4()

        async def invalidate_lock(*args, **kwargs):
            job.lock_token = replacement_lock_token
            await session.commit()
            return b""

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_runner_availability",
                return_value=_RunnerAvailability.AVAILABLE,
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_file_archives",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_code",
                new_callable=AsyncMock,
                side_effect=invalidate_lock,
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._submit_job_to_runner",
                return_value=_SubmitJobToRunnerResult(success=True),
            ),
        ):
            await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING
        assert job.lock_token == replacement_lock_token
        assert job.lock_token != original_lock_token

    async def test_updates_running_job(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        tmp_path: Path,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(dockerized=False),
            instance=instance,
            instance_assigned=True,
        )
        last_processed_at = job.last_processed_at

        with (
            patch.object(server_settings, "SERVER_DIR_PATH", tmp_path),
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as runner_client_cls,
        ):
            runner_client_mock = runner_client_cls.return_value
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[JobStateEvent(timestamp=1, state=JobStatus.RUNNING)],
                job_logs=[],
                runner_logs=[],
                last_updated=1,
            )
            await _process_job(session, worker, job)
            ssh_tunnel_cls.assert_called_once()

        await session.refresh(job)
        assert job.status == JobStatus.RUNNING
        assert job.runner_timestamp == 1

        job.last_processed_at = last_processed_at
        await session.commit()

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as runner_client_cls,
        ):
            runner_client_mock = runner_client_cls.return_value
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[JobStateEvent(timestamp=1, state=JobStatus.DONE, exit_status=0)],
                job_logs=[],
                runner_logs=[],
                last_updated=2,
            )
            await _process_job(session, worker, job)
            ssh_tunnel_cls.assert_called_once()

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.DONE_BY_RUNNER
        assert job.exit_status == 0
        assert job.runner_timestamp == 2

    async def test_running_job_disconnect_retries_then_terminates(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(dockerized=False),
            instance=instance,
            instance_assigned=True,
        )

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch("dstack._internal.server.services.runner.ssh.time.sleep"),
        ):
            ssh_tunnel_cls.side_effect = SSHError
            await _process_job(session, worker, job)
            assert ssh_tunnel_cls.call_count == 3

        await session.refresh(job)
        events = await list_events(session)
        assert job.status == JobStatus.RUNNING
        assert job.disconnected_at is not None
        assert len(events) == 1
        assert events[0].message == "Job became unreachable"

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch("dstack._internal.server.services.runner.ssh.time.sleep"),
            freeze_time(job.disconnected_at + timedelta(minutes=5)),
        ):
            ssh_tunnel_cls.side_effect = SSHError
            await _process_job(session, worker, job)
            assert ssh_tunnel_cls.call_count == 3

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.INSTANCE_UNREACHABLE

    @pytest.mark.parametrize(
        (
            "inactivity_duration",
            "no_connections_secs",
            "expected_status",
            "expected_termination_reason",
            "expected_inactivity_secs",
        ),
        [
            pytest.param(
                "1h",
                60 * 60 - 1,
                JobStatus.RUNNING,
                None,
                60 * 60 - 1,
                id="duration-not-exceeded",
            ),
            pytest.param(
                "1h",
                60 * 60,
                JobStatus.TERMINATING,
                JobTerminationReason.INACTIVITY_DURATION_EXCEEDED,
                60 * 60,
                id="duration-exceeded-exactly",
            ),
            pytest.param(
                "1h",
                60 * 60 + 1,
                JobStatus.TERMINATING,
                JobTerminationReason.INACTIVITY_DURATION_EXCEEDED,
                60 * 60 + 1,
                id="duration-exceeded",
            ),
            pytest.param("off", 60 * 60, JobStatus.RUNNING, None, None, id="duration-off"),
            pytest.param(False, 60 * 60, JobStatus.RUNNING, None, None, id="duration-false"),
            pytest.param(None, 60 * 60, JobStatus.RUNNING, None, None, id="duration-none"),
            pytest.param(
                "1h",
                None,
                JobStatus.TERMINATING,
                JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
                None,
                id="legacy-runner",
            ),
            pytest.param(
                None,
                None,
                JobStatus.RUNNING,
                None,
                None,
                id="legacy-runner-without-duration",
            ),
        ],
    )
    async def test_inactivity_duration(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        inactivity_duration,
        no_connections_secs: Optional[int],
        expected_status: JobStatus,
        expected_termination_reason: Optional[JobTerminationReason],
        expected_inactivity_secs: Optional[int],
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.RUNNING,
            run_name="test-run",
            run_spec=get_run_spec(
                run_name="test-run",
                repo_id=repo.name,
                configuration=DevEnvironmentConfiguration(
                    name="test-run",
                    ide="vscode",
                    inactivity_duration=inactivity_duration,
                ),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(),
            instance=instance,
            instance_assigned=True,
        )
        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as runner_client_cls,
        ):
            runner_client_mock = runner_client_cls.return_value
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[],
                job_logs=[],
                runner_logs=[],
                last_updated=0,
                no_connections_secs=no_connections_secs,
            )
            await _process_job(session, worker, job)
            ssh_tunnel_cls.assert_called_once()
            runner_client_mock.pull.assert_called_once()

        await session.refresh(job)
        assert job.status == expected_status
        assert job.termination_reason == expected_termination_reason
        assert job.inactivity_secs == expected_inactivity_secs

    @pytest.mark.parametrize(
        ["samples", "expected_status"],
        [
            pytest.param(
                [
                    (datetime(2023, 1, 1, 12, 25, 20, tzinfo=timezone.utc), 30),
                    (datetime(2023, 1, 1, 12, 25, 30, tzinfo=timezone.utc), 30),
                    (datetime(2023, 1, 1, 12, 29, 50, tzinfo=timezone.utc), 40),
                ],
                JobStatus.RUNNING,
                id="not-enough-points",
            ),
            pytest.param(
                [
                    (datetime(2023, 1, 1, 12, 20, 10, tzinfo=timezone.utc), 30),
                    (datetime(2023, 1, 1, 12, 20, 20, tzinfo=timezone.utc), 30),
                    (datetime(2023, 1, 1, 12, 29, 50, tzinfo=timezone.utc), 80),
                ],
                JobStatus.RUNNING,
                id="any-above-min",
            ),
            pytest.param(
                [
                    (datetime(2023, 1, 1, 12, 10, 10, tzinfo=timezone.utc), 80),
                    (datetime(2023, 1, 1, 12, 10, 20, tzinfo=timezone.utc), 80),
                    (datetime(2023, 1, 1, 12, 20, 10, tzinfo=timezone.utc), 30),
                    (datetime(2023, 1, 1, 12, 20, 20, tzinfo=timezone.utc), 30),
                    (datetime(2023, 1, 1, 12, 29, 50, tzinfo=timezone.utc), 40),
                ],
                JobStatus.TERMINATING,
                id="all-below-min",
            ),
        ],
    )
    @freeze_time(datetime(2023, 1, 1, 12, 30, tzinfo=timezone.utc))
    async def test_gpu_utilization(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        samples: list[tuple[datetime, int]],
        expected_status: JobStatus,
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.RUNNING,
            run_name="test-run",
            run_spec=get_run_spec(
                run_name="test-run",
                repo_id=repo.name,
                configuration=DevEnvironmentConfiguration(
                    name="test-run",
                    ide="vscode",
                    utilization_policy=UtilizationPolicy(
                        min_gpu_utilization=80,
                        time_window=600,
                    ),
                ),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(),
            instance=instance,
            instance_assigned=True,
            last_processed_at=datetime(2023, 1, 1, 11, 30, tzinfo=timezone.utc),
        )
        for timestamp, gpu_util in samples:
            await create_job_metrics_point(
                session=session,
                job_model=job,
                timestamp=timestamp,
                gpus_memory_usage_bytes=[1024, 1024],
                gpus_util_percent=[gpu_util, 100],
            )

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as ssh_tunnel_cls,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as runner_client_cls,
        ):
            runner_client_mock = runner_client_cls.return_value
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[],
                job_logs=[],
                runner_logs=[],
                last_updated=0,
                no_connections_secs=0,
            )
            await _process_job(session, worker, job)
            ssh_tunnel_cls.assert_called_once()
            runner_client_mock.pull.assert_called_once()

        await session.refresh(job)
        assert job.status == expected_status
        if expected_status == JobStatus.TERMINATING:
            assert (
                job.termination_reason == JobTerminationReason.TERMINATED_DUE_TO_UTILIZATION_POLICY
            )
            assert job.termination_reason_message == (
                "The job GPU utilization below 80% for 600 seconds"
            )
        else:
            assert job.termination_reason is None
            assert job.termination_reason_message is None

    @pytest.mark.parametrize("probe_count", [1, 2])
    async def test_creates_probe_models_and_not_registers_service_replica(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
        probe_count: int,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80,
                    image="ubuntu",
                    probes=[ProbeConfig(type="http", url=f"/{i}") for i in range(probe_count)],
                ),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING

        assert len(job.probes) == 0
        await _process_job(session, worker, job)

        await session.refresh(job)
        job = (
            await session.execute(
                select(JobModel)
                .where(JobModel.id == job.id)
                .options(selectinload(JobModel.probes))
            )
        ).scalar_one()
        assert job.status == JobStatus.RUNNING
        assert [probe.probe_num for probe in job.probes] == list(range(probe_count))
        assert not job.registered

    async def test_registers_service_replica_immediately_if_no_probes(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
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
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(port=80, image="ubuntu"),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING

        await _process_job(session, worker, job)

        await session.refresh(job)
        assert job.status == JobStatus.RUNNING
        assert job.registered
        events = await list_events(session)
        assert {event.message for event in events} == {
            "Job status changed PULLING -> RUNNING",
            "Service replica registered to receive requests",
        }

    @pytest.mark.parametrize(
        ("probes", "expect_to_register"),
        [
            ([_ProbeSetup(success_streak=0, ready_after=1)], False),
            ([_ProbeSetup(success_streak=1, ready_after=1)], True),
            (
                [
                    _ProbeSetup(success_streak=1, ready_after=1),
                    _ProbeSetup(success_streak=1, ready_after=2),
                ],
                False,
            ),
            (
                [
                    _ProbeSetup(success_streak=1, ready_after=1),
                    _ProbeSetup(success_streak=3, ready_after=2),
                ],
                True,
            ),
        ],
    )
    async def test_registers_service_replica_only_after_probes_pass(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        runner_client_mock: Mock,
        probes: list[_ProbeSetup],
        expect_to_register: bool,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80,
                    image="ubuntu",
                    probes=[
                        ProbeConfig(type="http", url=f"/{i}", ready_after=probe.ready_after)
                        for i, probe in enumerate(probes)
                    ],
                ),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
            registered=False,
        )
        for i, probe in enumerate(probes):
            await create_probe(
                session=session,
                job=job,
                probe_num=i,
                success_streak=probe.success_streak,
            )
        runner_client_mock.pull.return_value = PullResponse(
            job_states=[],
            job_logs=[],
            runner_logs=[],
            last_updated=0,
        )

        await _process_job(session, worker, job)

        await session.refresh(job)
        events = await list_events(session)
        if expect_to_register:
            assert job.registered
            assert len(events) == 1
            assert events[0].message == "Service replica registered to receive requests"
        else:
            assert not job.registered
            assert not events

    async def test_registers_service_replica_in_gateway(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
        mock_gateway_connection: AsyncMock,
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
        )
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
            status=GatewayStatus.RUNNING,
            name="test-gateway",
            wildcard_domain="example.com",
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80, image="ubuntu", gateway="test-gateway"
                ),
            ),
            gateway=gateway,
        )
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            fleet=fleet,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING

        await _process_job(session, worker, job)

        await session.refresh(job)
        assert job.status == JobStatus.RUNNING
        assert job.registered
        events = await list_events(session)
        assert {event.message for event in events} == {
            "Job status changed PULLING -> RUNNING",
            "Service replica registered to receive requests",
        }
        mock_gateway_connection.return_value.client.return_value.__aenter__.return_value.register_replica.assert_called_once_with(
            run=ANY,
            job_spec=ANY,
            job_submission=ANY,
            instance_project_ssh_private_key=None,
            ssh_head_proxy=None,
            ssh_head_proxy_private_key=None,
        )

    async def test_registers_service_replica_in_gateway_when_running_on_imported_instance(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
        ssh_tunnel_mock: Mock,
        shim_client_mock: Mock,
        runner_client_mock: Mock,
        mock_gateway_connection: AsyncMock,
    ):
        user = await create_user(session=session)
        exporter_project = await create_project(
            session=session, name="exporter", owner=user, ssh_private_key="exporter-private-key"
        )
        importer_project = await create_project(session=session, name="importer", owner=user)
        fleet = await create_fleet(session=session, project=exporter_project)
        instance = await create_instance(
            session=session,
            project=exporter_project,
            status=InstanceStatus.BUSY,
            fleet=fleet,
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[fleet],
        )
        repo = await create_repo(session=session, project_id=importer_project.id)
        backend = await create_backend(session=session, project_id=importer_project.id)
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
        )
        gateway = await create_gateway(
            session=session,
            project_id=importer_project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
            status=GatewayStatus.RUNNING,
            name="test-gateway",
            wildcard_domain="example.com",
        )
        run = await create_run(
            session=session,
            project=importer_project,
            repo=repo,
            user=user,
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80, image="ubuntu", gateway="test-gateway"
                ),
            ),
            gateway=gateway,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
        )
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING

        await _process_job(session, worker, job)

        await session.refresh(job)
        assert job.status == JobStatus.RUNNING
        assert job.registered
        events = await list_events(session)
        assert {event.message for event in events} == {
            "Job status changed PULLING -> RUNNING",
            "Service replica registered to receive requests",
        }
        mock_gateway_connection.return_value.client.return_value.__aenter__.return_value.register_replica.assert_called_once_with(
            run=ANY,
            job_spec=ANY,
            job_submission=ANY,
            instance_project_ssh_private_key="exporter-private-key",
            ssh_head_proxy=None,
            ssh_head_proxy_private_key=None,
        )

    async def test_apply_skips_probe_insert_when_lock_token_changes_after_processing(
        self,
        test_db,
        session: AsyncSession,
        worker: JobRunningWorker,
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
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80,
                    image="ubuntu",
                    probes=[ProbeConfig(type="http", url="/health")],
                ),
            ),
        )
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
        )
        _lock_job(job)
        await session.commit()
        replacement_lock_token = uuid.uuid4()
        shim_client_mock.get_task.return_value.status = TaskStatus.RUNNING

        async def invalidate_lock(*args, **kwargs):
            job.lock_token = replacement_lock_token
            await session.commit()
            return b""

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_file_archives",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._get_job_code",
                new_callable=AsyncMock,
                side_effect=invalidate_lock,
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_running._submit_job_to_runner",
                return_value=_SubmitJobToRunnerResult(
                    success=True,
                    set_running_status=True,
                ),
            ),
        ):
            await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        assert job.status == JobStatus.PULLING
        assert job.lock_token == replacement_lock_token
        probes = (
            (await session.execute(select(ProbeModel).where(ProbeModel.job_id == job.id)))
            .scalars()
            .all()
        )
        assert probes == []
