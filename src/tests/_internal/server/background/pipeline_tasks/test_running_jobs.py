import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal import settings
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import StartupOrder
from dstack._internal.core.models.runs import (
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
    RunStatus,
)
from dstack._internal.core.models.volumes import InstanceMountPoint, VolumeMountPoint, VolumeStatus
from dstack._internal.server.background.pipeline_tasks.jobs_running import (
    JobRunningFetcher,
    JobRunningPipeline,
    JobRunningPipelineItem,
    JobRunningWorker,
    _RunnerAvailability,
)
from dstack._internal.server.schemas.runner import (
    HealthcheckResponse,
    JobInfoResponse,
    PortMapping,
    TaskStatus,
)
from dstack._internal.server.services.volumes import volume_model_to_volume
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
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
    mock = MagicMock()
    monkeypatch.setattr("dstack._internal.server.services.runner.ssh.SSHTunnel", mock)
    return mock


@pytest.fixture
def shim_client_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock()
    mock.healthcheck.return_value = HealthcheckResponse(service="dstack-shim", version="latest")
    monkeypatch.setattr(
        "dstack._internal.server.services.runner.client.ShimClient", Mock(return_value=mock)
    )
    return mock


@pytest.fixture
def runner_client_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock()
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
            return True

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
                return_value=True,
            ),
        ):
            await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING
        assert job.lock_token == replacement_lock_token
        assert job.lock_token != original_lock_token
