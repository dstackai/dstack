from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType, Resources
from dstack._internal.core.models.runs import JobProvisioningData, JobStatus
from dstack._internal.server import settings
from dstack._internal.server.background.tasks.process_running_jobs import process_running_jobs
from dstack._internal.server.models import JobModel
from dstack._internal.server.schemas.runner import JobStateEvent, PullResponse
from tests._internal.server.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)


def get_job_provisioning_data() -> JobProvisioningData:
    return JobProvisioningData(
        backend=BackendType.AWS,
        instance_type=InstanceType(
            name="instance",
            resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
        ),
        instance_id="instance_id",
        hostname="127.0.0.4",
        region="us-east-1",
        price=10.5,
        username="ubuntu",
        ssh_port=22,
        dockerized=True,
    )


class TestProcessRunningJobs:
    @pytest.mark.asyncio
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
        job_provisioning_data = get_job_provisioning_data()
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            submitted_at=datetime(2023, 1, 2, 5, 12, 30, 5, tzinfo=timezone.utc),
            job_provisioning_data=job_provisioning_data,
        )
        with patch(
            "dstack._internal.core.services.ssh.tunnel.RunnerTunnel"
        ) as RunnerTunnelMock, patch(
            "dstack._internal.server.services.runner.client.RunnerClient"
        ) as RunnerClientMock, patch(
            "dstack._internal.utils.common.get_current_datetime"
        ) as datetime_mock:
            datetime_mock.return_value = datetime(2023, 1, 2, 5, 12, 30, 10, tzinfo=timezone.utc)
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.healthcheck = Mock()
            runner_client_mock.healthcheck.return_value = False
            await process_running_jobs()
            RunnerTunnelMock.assert_called_once()
            runner_client_mock.healthcheck.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
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
        job_provisioning_data = get_job_provisioning_data()
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            job_provisioning_data=job_provisioning_data,
        )
        with patch(
            "dstack._internal.core.services.ssh.tunnel.RunnerTunnel"
        ) as RunnerTunnelMock, patch(
            "dstack._internal.server.services.runner.client.RunnerClient"
        ) as RunnerClientMock:
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.healthcheck = Mock()
            runner_client_mock.healthcheck.return_value = True
            runner_client_mock.submit_job = Mock()
            runner_client_mock.upload_code = Mock()
            runner_client_mock.run_job = Mock()
            await process_running_jobs()
            RunnerTunnelMock.assert_called_once()
            runner_client_mock.healthcheck.assert_called_once()
            runner_client_mock.submit_job.assert_called_once()
            runner_client_mock.upload_code.assert_called_once()
            runner_client_mock.run_job.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.RUNNING

    @pytest.mark.asyncio
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
        job_provisioning_data = get_job_provisioning_data()
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=job_provisioning_data,
        )
        with patch(
            "dstack._internal.core.services.ssh.tunnel.RunnerTunnel"
        ) as RunnerTunnelMock, patch(
            "dstack._internal.server.services.runner.client.RunnerClient"
        ) as RunnerClientMock, patch.object(
            settings, "SERVER_DIR_PATH", tmp_path
        ):
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.pull = Mock()
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[JobStateEvent(timestamp=1, state=JobStatus.RUNNING)],
                job_logs=[],
                runner_logs=[],
                last_updated=1,
            )
            await process_running_jobs()
            RunnerTunnelMock.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert job.runner_timestamp == 1
        with patch(
            "dstack._internal.core.services.ssh.tunnel.RunnerTunnel"
        ) as RunnerTunnelMock, patch(
            "dstack._internal.server.services.runner.client.RunnerClient"
        ) as RunnerClientMock:
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.pull = Mock()
            runner_client_mock.pull.return_value = PullResponse(
                job_states=[JobStateEvent(timestamp=1, state=JobStatus.DONE)],
                job_logs=[],
                runner_logs=[],
                last_updated=2,
            )
            await process_running_jobs()
            RunnerTunnelMock.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.DONE
        assert job.runner_timestamp == 2
