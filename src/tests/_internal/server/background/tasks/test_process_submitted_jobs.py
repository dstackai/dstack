from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile, ProfileRetryPolicy
from dstack._internal.core.models.runs import (
    InstanceStatus,
    JobProvisioningData,
    JobStatus,
    JobTerminationReason,
)
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs
from dstack._internal.server.models import JobModel, ProjectModel
from dstack._internal.server.services.pools import (
    get_or_create_pool_by_name,
)
from dstack._internal.server.testing.common import (
    create_instance,
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
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY

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
        offer = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=1.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = JobProvisioningData(
                backend=offer.backend,
                instance_type=offer.instance,
                instance_id="instance_id",
                hostname="1.1.1.1",
                internal_ip=None,
                region=offer.region,
                price=offer.price,
                username="ubuntu",
                ssh_port=22,
                ssh_proxy=None,
                dockerized=True,
                backend_data=None,
            )
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

        res = await session.execute(
            select(ProjectModel)
            .where(ProjectModel.id == project.id)
            .options(joinedload(ProjectModel.default_pool))
        )
        project = res.scalar_one()
        assert project.default_pool.name == DEFAULT_POOL_NAME

        instance_offer = InstanceOfferWithAvailability.parse_raw(
            project.default_pool.instances[0].offer
        )
        assert offer == instance_offer

        pool_job_provisioning_data = project.default_pool.instances[0].job_provisioning_data
        assert pool_job_provisioning_data == job.job_provisioning_data

    @pytest.mark.asyncio
    async def test_fails_job_when_no_capacity(self, test_db, session: AsyncSession):
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
                    retry_policy=ProfileRetryPolicy(retry=True, duration=3600),
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
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY

        res = await session.execute(
            select(ProjectModel)
            .where(ProjectModel.id == project.id)
            .options(joinedload(ProjectModel.default_pool))
        )
        project = res.scalar_one()
        assert not project.default_pool.instances

    @pytest.mark.asyncio
    async def test_job_with_instance(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        pool = await get_or_create_pool_by_name(session, project, pool_name=None)
        instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            status=InstanceStatus.IDLE,
        )
        await session.refresh(pool)
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
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.scalar_one()
        assert job.status == JobStatus.PROVISIONING
        assert job.instance is not None and job.instance.id == instance.id
