import json
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import ScalingSpec, ServiceConfiguration
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import (
    JobStatus,
    RunStatus,
)
from dstack._internal.server.background.pipeline_tasks.runs import RunWorker
from dstack._internal.server.models import JobModel
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
)
from dstack._internal.utils.common import get_current_datetime
from tests._internal.server.background.pipeline_tasks.test_runs.helpers import (
    lock_run,
    run_to_pipeline_item,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock")
class TestRunPendingWorker:
    async def test_submits_non_service_run_and_creates_job(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.PENDING,
            resubmission_attempt=0,
            next_triggered_at=None,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert run.desired_replica_count == 1
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

        res = await session.execute(select(JobModel).where(JobModel.run_id == run.id))
        jobs = list(res.scalars().all())
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.SUBMITTED
        assert jobs[0].replica_num == 0
        assert jobs[0].submission_num == 0

    async def test_skips_retrying_run_when_delay_not_met(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.PENDING,
            resubmission_attempt=1,
        )
        # Create a job with recent last_processed_at so retry delay is not met
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            last_processed_at=get_current_datetime(),
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.PENDING
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

    async def test_resubmits_retrying_run_after_delay(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.PENDING,
            resubmission_attempt=1,
        )
        # Create a job with old last_processed_at so retry delay is met (>15s for attempt 1)
        old_time = get_current_datetime() - timedelta(minutes=1)
        old_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            last_processed_at=old_time,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert run.desired_replica_count == 1
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

        # Should have created a new job (retry of the failed one)
        res = await session.execute(
            select(JobModel)
            .where(JobModel.run_id == run.id)
            .order_by(JobModel.submitted_at.desc())
        )
        jobs = list(res.scalars().all())
        assert len(jobs) == 2
        new_job = next(j for j in jobs if j.id != old_job.id)
        assert new_job.status == JobStatus.SUBMITTED
        assert new_job.replica_num == old_job.replica_num
        assert new_job.submission_num == old_job.submission_num + 1

    async def test_noops_when_run_lock_changes_after_processing(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.PENDING,
            resubmission_attempt=0,
            next_triggered_at=None,
        )
        lock_run(run)
        await session.commit()
        item = run_to_pipeline_item(run)
        new_lock_token = uuid.uuid4()

        from dstack._internal.server.background.pipeline_tasks.runs.pending import (
            PendingResult,
            PendingRunUpdateMap,
        )

        async def intercept_process(context):
            # Change the lock token to simulate concurrent modification
            run.lock_token = new_lock_token
            run.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
            await session.commit()
            # Return a result that would normally cause a state change
            return PendingResult(
                run_update_map=PendingRunUpdateMap(
                    status=RunStatus.SUBMITTED,
                    desired_replica_count=1,
                ),
                new_job_models=[],
            )

        with patch(
            "dstack._internal.server.background.pipeline_tasks.runs.pending.process_pending_run",
            new=AsyncMock(side_effect=intercept_process),
        ):
            await worker.process(item)

        await session.refresh(run)
        assert run.status == RunStatus.PENDING
        assert run.lock_token == new_lock_token

    async def test_submits_service_run_and_creates_jobs(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo Hi!"],
                replicas=Range[int](min=2, max=2),
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.PENDING,
            resubmission_attempt=0,
            next_triggered_at=None,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert run.desired_replica_count == 2
        assert run.desired_replica_counts is not None
        counts = json.loads(run.desired_replica_counts)
        assert counts == {"0": 2}
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

        res = await session.execute(select(JobModel).where(JobModel.run_id == run.id))
        jobs = list(res.scalars().all())
        assert len(jobs) == 2
        replica_nums = sorted(j.replica_num for j in jobs)
        assert replica_nums == [0, 1]
        assert all(j.status == JobStatus.SUBMITTED for j in jobs)
        assert all(j.submission_num == 0 for j in jobs)

    async def test_noops_for_zero_scaled_service(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo Hi!"],
                replicas=Range[int](min=0, max=2),
                scaling=ScalingSpec(metric="rps", target=10),
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.PENDING,
            resubmission_attempt=0,
            next_triggered_at=None,
        )
        # Set desired_replica_count=0 and desired_replica_counts to match zero-scaled state.
        run.desired_replica_count = 0
        run.desired_replica_counts = json.dumps({"0": 0})
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.PENDING
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

        res = await session.execute(select(JobModel).where(JobModel.run_id == run.id))
        jobs = list(res.scalars().all())
        assert len(jobs) == 0
