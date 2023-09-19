import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import UUID

import botocore.exceptions
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.backends
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs
from dstack._internal.server.models import JobModel
from tests.server.common import create_job, create_project, create_repo, create_run, create_user


class TestProcessSubmittedJobs:
    @pytest.mark.asyncio
    async def test_fails_job_when_no_backends(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=submitted_at,
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=submitted_at,
            last_processed_at=submitted_at,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_fails_job_when_no_backends(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=submitted_at,
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=submitted_at,
            last_processed_at=submitted_at,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_provisiones_job(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=submitted_at,
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=submitted_at,
            last_processed_at=submitted_at,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.get_instance_candidates.return_value = [
                InstanceOfferWithAvailability(
                    instance=InstanceType(
                        name="instance",
                        resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
                    ),
                    region="us",
                    price=1.0,
                    availability=InstanceAvailability.AVAILABLE,
                )
            ]
            backend_mock.compute.return_value.run_job.return_value = LaunchedInstanceInfo(
                instance_id="instance_id",
                region="us",
                ip_address="1.1.1.1",
            )
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.get_instance_candidates.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING
