import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import Schedule
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.background.pipeline_tasks.jobs_terminating import (
    JobTerminatingPipeline,
)
from dstack._internal.server.background.pipeline_tasks.runs import RunPipeline, RunWorker
from dstack._internal.server.background.pipeline_tasks.runs.terminating import (
    TerminatingResult,
    process_terminating_run,
)
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_run_spec,
)
from dstack._internal.utils.common import get_current_datetime
from tests._internal.server.background.pipeline_tasks.test_runs.helpers import (
    lock_run,
    run_to_pipeline_item,
)


def _lock_job(
    job_model,
    *,
    lock_owner: str = RunPipeline.__name__,
    lock_expires_at: Optional[datetime] = None,
) -> None:
    if lock_expires_at is None:
        lock_expires_at = get_current_datetime() + timedelta(seconds=30)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_expires_at = lock_expires_at
    job_model.lock_owner = lock_owner


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock")
class TestRunTerminatingWorker:
    async def test_transitions_running_jobs_to_terminating(
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
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.JOB_FAILED,
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
        lock_run(run)
        await session.commit()
        await worker.process(run_to_pipeline_item(run))

        await session.refresh(job)
        await session.refresh(run)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        assert job.graceful_termination_attempts == 0
        assert job.skip_min_processing_interval
        assert job.remove_at is None
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner is None
        assert run.status == RunStatus.TERMINATING
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

    async def test_updates_delayed_and_regular_jobs_separately(
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
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.JOB_FAILED,
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        delayed_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(),
            instance=instance,
            instance_assigned=True,
        )
        regular_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            job_num=1,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(delayed_job)
        await session.refresh(regular_job)
        assert delayed_job.status == JobStatus.TERMINATING
        assert delayed_job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        assert delayed_job.graceful_termination_attempts == 0
        assert delayed_job.skip_min_processing_interval
        assert delayed_job.remove_at is None
        assert regular_job.status == JobStatus.TERMINATING
        assert regular_job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        assert regular_job.graceful_termination_attempts is None
        assert regular_job.skip_min_processing_interval
        assert regular_job.remove_at is None

    async def test_finishes_non_scheduled_run_when_all_jobs_are_finished(
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
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.JOB_FAILED,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.EXECUTOR_ERROR,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.FAILED
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

    @freeze_time(datetime(2023, 1, 2, 3, 10, tzinfo=timezone.utc))
    async def test_reschedules_scheduled_run_and_clears_fleet(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="scheduled-run",
            configuration=TaskConfiguration(
                nodes=1,
                schedule=Schedule(cron="15 * * * *"),
                commands=["echo Hi!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
            run_name="scheduled-run",
            run_spec=run_spec,
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.ALL_JOBS_DONE,
            resubmission_attempt=1,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.PENDING
        assert run.next_triggered_at == datetime(2023, 1, 2, 3, 15, tzinfo=timezone.utc)
        assert run.resubmission_attempt == 0
        assert run.fleet_id is None
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

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
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.JOB_FAILED,
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
        lock_run(run)
        await session.commit()
        item = run_to_pipeline_item(run)
        new_lock_token = uuid.uuid4()
        original_process_terminating_run = process_terminating_run

        async def change_run_lock(context) -> TerminatingResult:
            run.lock_token = new_lock_token
            run.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
            await session.commit()
            return await original_process_terminating_run(context)

        with patch(
            "dstack._internal.server.background.pipeline_tasks.runs.terminating.process_terminating_run",
            new=AsyncMock(side_effect=change_run_lock),
        ):
            await worker.process(item)

        await session.refresh(run)
        await session.refresh(job)
        assert run.status == RunStatus.TERMINATING
        assert run.lock_token == new_lock_token
        assert run.lock_owner == RunPipeline.__name__
        assert job.status == JobStatus.RUNNING
        assert job.graceful_termination_attempts is None
        assert job.remove_at is None
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner is None

    async def test_resets_run_lock_when_related_job_is_locked_by_another_pipeline(
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
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.JOB_FAILED,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
        )
        _lock_job(job, lock_owner=JobTerminatingPipeline.__name__)
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        await session.refresh(job)
        assert run.status == RunStatus.TERMINATING
        assert run.lock_owner == RunPipeline.__name__
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert job.status == JobStatus.SUBMITTED
        assert job.lock_owner == JobTerminatingPipeline.__name__

    async def test_reclaims_expired_same_owner_related_job_lock(
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
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.JOB_FAILED,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
        )
        _lock_job(
            job,
            lock_owner=RunPipeline.__name__,
            lock_expires_at=get_current_datetime() - timedelta(minutes=1),
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner is None
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None

    async def test_ignores_already_terminating_jobs_when_locking_related_jobs(
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
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.JOB_FAILED,
        )
        terminating_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_SERVER,
        )
        submitted_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            job_num=1,
        )
        _lock_job(terminating_job, lock_owner=JobTerminatingPipeline.__name__)
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        await session.refresh(terminating_job)
        await session.refresh(submitted_job)
        assert terminating_job.status == JobStatus.TERMINATING
        assert terminating_job.lock_owner == JobTerminatingPipeline.__name__
        assert submitted_job.status == JobStatus.TERMINATING
        assert submitted_job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        assert submitted_job.lock_token is None
        assert submitted_job.lock_expires_at is None
        assert submitted_job.lock_owner is None
        assert run.lock_token is None
        assert run.lock_expires_at is None
        assert run.lock_owner is None
