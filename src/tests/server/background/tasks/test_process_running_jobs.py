import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.runs import JobProvisioningData, JobStatus
from dstack._internal.server.background.tasks.process_running_jobs import process_running_jobs
from dstack._internal.server.models import JobModel
from tests.server.common import create_job, create_project, create_repo, create_run, create_user


def get_job_provisioning_data() -> JobProvisioningData:
    return JobProvisioningData(
        hostname="127.0.0.4",
        instance_type=InstanceType(
            name="instance",
            resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
        ),
        instance_id="instance_id",
        region="us-east-1",
        price=10.5,
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
            job_provisioning_data=job_provisioning_data,
        )
        with patch(
            "dstack._internal.server.services.runner.ssh.SSHTunnel"
        ) as SSHTunnelMock, patch(
            "dstack._internal.server.services.runner.client.AsyncRunnerClient"
        ) as AsyncRunnerClientMock:
            runner_client_mock = AsyncRunnerClientMock.return_value
            runner_client_mock.healthcheck = AsyncMock()
            runner_client_mock.healthcheck.return_value = False
            await process_running_jobs()
            SSHTunnelMock.assert_called_once()
            runner_client_mock.healthcheck.assert_awaited_once()
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
            "dstack._internal.server.services.runner.ssh.SSHTunnel"
        ) as SSHTunnelMock, patch(
            "dstack._internal.server.services.runner.client.AsyncRunnerClient"
        ) as AsyncRunnerClientMock:
            runner_client_mock = AsyncRunnerClientMock.return_value
            runner_client_mock.healthcheck = AsyncMock()
            runner_client_mock.healthcheck.return_value = True
            runner_client_mock.submit_job = AsyncMock()
            runner_client_mock.upload_code = AsyncMock()
            runner_client_mock.run_job = AsyncMock()
            await process_running_jobs()
            SSHTunnelMock.assert_called_once()
            runner_client_mock.healthcheck.assert_awaited_once()
            runner_client_mock.submit_job.assert_awaited_once()
            runner_client_mock.upload_code.assert_awaited_once()
            runner_client_mock.run_job.assert_awaited_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.RUNNING
