import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.profiles import Profile, ProfileRetryPolicy
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs
from tests._internal.server.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
)


class TestProcessSubmittedJobs:
    @pytest.mark.asyncio
    async def test_fails_job_when_no_backends(self, test_db, session: AsyncSession):
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
        job = await create_job(
            session=session,
            run=run,
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
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [
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
                username="ubuntu",
                ssh_port=22,
                dockerized=True,
            )
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_transitions_job_with_retry_to_pending_on_no_capacity(
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
            run_name="test-run",
            run_spec=get_run_spec(
                run_name="test-run",
                repo_id=repo.name,
                profile=Profile(
                    name="default",
                    retry_policy=ProfileRetryPolicy(retry=True, limit=3600),
                ),
            ),
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=datetime(2023, 1, 2, 3, 0, 0, tzinfo=timezone.utc),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = datetime(2023, 1, 2, 3, 30, 0, tzinfo=timezone.utc)
            await process_submitted_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_transitions_job_with_outdated_retry_to_failed_on_no_capacity(
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
            run_name="test-run",
            run_spec=get_run_spec(
                run_name="test-run",
                repo_id=repo.name,
                profile=Profile(
                    name="default",
                    retry_policy=ProfileRetryPolicy(retry=True, limit=3600),
                ),
            ),
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=datetime(2023, 1, 2, 3, 0, 0, tzinfo=timezone.utc),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = datetime(2023, 1, 2, 5, 0, 0, tzinfo=timezone.utc)
            await process_submitted_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.FAILED
