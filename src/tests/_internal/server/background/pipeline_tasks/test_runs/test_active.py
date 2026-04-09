import json
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import (
    ScalingSpec,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import (
    Profile,
    ProfileRetry,
    RetryEvent,
    Schedule,
    StopCriteria,
)
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.background.pipeline_tasks.runs import RunWorker
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs import get_job_spec
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


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock")
class TestRunActiveWorker:
    async def test_transitions_submitted_to_provisioning(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.SUBMITTED,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            instance=instance,
            instance_assigned=True,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING
        assert run.lock_token is None

    async def test_transitions_provisioning_to_running(
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
            status=RunStatus.PROVISIONING,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert run.lock_token is None

    async def test_terminates_run_when_all_jobs_done(
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
            status=RunStatus.RUNNING,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.DONE,
            termination_reason=JobTerminationReason.DONE_BY_RUNNER,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.ALL_JOBS_DONE
        assert run.lock_token is None

    async def test_terminates_run_on_job_failure(
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
            status=RunStatus.RUNNING,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.JOB_FAILED
        assert run.lock_token is None

    async def test_retries_failed_replica_within_retry_duration(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """When a replica fails within retry duration, the run goes to PENDING with
        resubmission_attempt incremented. The pending worker then creates the new submission."""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(
                name="default",
                retry=ProfileRetry(duration=3600, on_events=[RetryEvent.ERROR]),
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
            status=RunStatus.RUNNING,
            resubmission_attempt=0,
        )
        old_time = get_current_datetime() - timedelta(minutes=5)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
            job_provisioning_data=get_job_provisioning_data(),
            last_processed_at=old_time,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        # Retryable failure → PENDING with resubmission_attempt incremented
        assert run.status == RunStatus.PENDING
        assert run.resubmission_attempt == 1
        assert run.lock_token is None

    async def test_retries_no_capacity_replica_and_keeps_service_running(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(
                name="default",
                retry=ProfileRetry(duration=3600, on_events=[RetryEvent.INTERRUPTION]),
            ),
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
            run_spec=run_spec,
            status=RunStatus.RUNNING,
        )
        interrupted_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            submitted_at=run.submitted_at,
            last_processed_at=run.last_processed_at,
            replica_num=0,
            job_provisioning_data=get_job_provisioning_data(),
        )
        healthy_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            submitted_at=run.submitted_at,
            last_processed_at=run.last_processed_at,
            replica_num=1,
            job_provisioning_data=get_job_provisioning_data(),
        )
        lock_run(run)
        await session.commit()

        now = run.submitted_at + timedelta(minutes=3)
        with patch(
            "dstack._internal.server.background.pipeline_tasks.runs.active.get_current_datetime",
            return_value=now,
        ):
            await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        await session.refresh(interrupted_job)
        await session.refresh(healthy_job)

        jobs = list(
            (
                await session.execute(
                    select(JobModel)
                    .where(JobModel.run_id == run.id)
                    .order_by(JobModel.replica_num, JobModel.submission_num)
                )
            ).scalars()
        )
        retried_job = next(job for job in jobs if job.replica_num == 0 and job.submission_num == 1)

        assert run.status == RunStatus.RUNNING
        assert interrupted_job.status == JobStatus.TERMINATING
        assert (
            interrupted_job.termination_reason == JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
        )
        assert healthy_job.status == JobStatus.RUNNING
        assert retried_job.status == JobStatus.SUBMITTED
        assert len(jobs) == 3

    async def test_retries_scheduled_run_no_capacity_from_trigger_time(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(
                name="default",
                retry=ProfileRetry(duration=3600, on_events=[RetryEvent.NO_CAPACITY]),
            ),
            configuration=TaskConfiguration(
                commands=["echo hello"],
                schedule=Schedule(cron="15 * * * *"),
            ),
        )
        trigger_time = get_current_datetime() - timedelta(minutes=5)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
            status=RunStatus.SUBMITTED,
            submitted_at=get_current_datetime() - timedelta(hours=2),
            next_triggered_at=trigger_time,
            resubmission_attempt=0,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )
        lock_run(run)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.runs.active.get_current_datetime",
            return_value=trigger_time + timedelta(minutes=10),
        ):
            await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.PENDING
        assert run.resubmission_attempt == 1
        assert run.lock_token is None

    async def test_terminates_scheduled_run_when_no_capacity_retry_exceeded_from_trigger_time(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(
                name="default",
                retry=ProfileRetry(duration=600, on_events=[RetryEvent.NO_CAPACITY]),
            ),
            configuration=TaskConfiguration(
                commands=["echo hello"],
                schedule=Schedule(cron="15 * * * *"),
            ),
        )
        trigger_time = get_current_datetime() - timedelta(minutes=20)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
            status=RunStatus.SUBMITTED,
            submitted_at=get_current_datetime() - timedelta(hours=2),
            next_triggered_at=trigger_time,
            resubmission_attempt=0,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )
        lock_run(run)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.runs.active.get_current_datetime",
            return_value=trigger_time + timedelta(minutes=20),
        ):
            await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.RETRY_LIMIT_EXCEEDED
        assert run.lock_token is None

    async def test_retrying_multinode_replica_terminates_active_sibling_jobs(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(
                name="default",
                retry=ProfileRetry(duration=3600, on_events=[RetryEvent.ERROR]),
            ),
            configuration=TaskConfiguration(
                commands=["echo hello"],
                nodes=2,
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
            status=RunStatus.RUNNING,
        )
        failed_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
            replica_num=0,
            job_num=0,
            job_provisioning_data=get_job_provisioning_data(),
            last_processed_at=run.submitted_at,
        )
        running_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
            job_num=1,
            job_provisioning_data=get_job_provisioning_data(),
            last_processed_at=run.submitted_at,
        )
        lock_run(run)
        await session.commit()

        now = run.submitted_at + timedelta(minutes=1)
        with patch(
            "dstack._internal.server.background.pipeline_tasks.runs.active.get_current_datetime",
            return_value=now,
        ):
            await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        await session.refresh(failed_job)
        await session.refresh(running_job)

        assert run.status == RunStatus.PENDING
        assert failed_job.status == JobStatus.FAILED
        assert running_job.status == JobStatus.TERMINATING
        assert running_job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        assert running_job.termination_reason_message == "Run is to be resubmitted"

    async def test_transitions_to_pending_when_retry_duration_exceeded(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(
                name="default",
                retry=ProfileRetry(duration=60, on_events=[RetryEvent.ERROR]),
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
            status=RunStatus.RUNNING,
            resubmission_attempt=0,
        )
        # Last provisioned long ago so retry duration is exceeded
        very_old_time = get_current_datetime() - timedelta(hours=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
            job_provisioning_data=get_job_provisioning_data(),
            last_processed_at=very_old_time,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.RETRY_LIMIT_EXCEEDED
        assert run.lock_token is None

    async def test_stops_on_master_done(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(name="default", stop_criteria=StopCriteria.MASTER_DONE),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
            status=RunStatus.RUNNING,
        )
        # Master job (job_num=0) is done
        await create_job(
            session=session,
            run=run,
            status=JobStatus.DONE,
            termination_reason=JobTerminationReason.DONE_BY_RUNNER,
            job_num=0,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.ALL_JOBS_DONE

    async def test_sets_fleet_id_from_job_instance(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.SUBMITTED,
        )
        assert run.fleet_id is None
        await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            instance=instance,
            instance_assigned=True,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.fleet_id == fleet.id

    async def test_service_noop_when_at_desired_count(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Service with 1 RUNNING replica and desired=1 stays RUNNING, no new jobs."""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo Hi!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert run.desired_replica_count == 1
        assert run.desired_replica_counts is not None
        counts = json.loads(run.desired_replica_counts)
        assert counts == {"0": 1}
        assert run.lock_token is None

    async def test_service_scale_up(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Service with min=2 and 1 RUNNING replica creates 1 new SUBMITTED job."""
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
            status=RunStatus.SUBMITTED,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert run.desired_replica_count == 2

        res = await session.execute(
            select(JobModel).where(JobModel.run_id == run.id).order_by(JobModel.replica_num)
        )
        jobs = list(res.scalars().all())
        assert len(jobs) == 2
        assert jobs[0].status == JobStatus.RUNNING
        assert jobs[0].replica_num == 0
        assert jobs[1].status == JobStatus.SUBMITTED
        assert jobs[1].replica_num == 1

    async def test_service_scale_down(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Service with min=1 and 2 RUNNING replicas terminates 1 with SCALED_DOWN."""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo Hi!"],
                replicas=Range[int](min=1, max=1),
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
        )
        run.desired_replica_count = 2
        run.desired_replica_counts = json.dumps({"0": 2})
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=1,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert run.desired_replica_count == 1

        res = await session.execute(
            select(JobModel).where(JobModel.run_id == run.id).order_by(JobModel.replica_num)
        )
        jobs = list(res.scalars().all())
        assert len(jobs) == 2
        # One should remain RUNNING, the other should be TERMINATING with SCALED_DOWN
        running = [j for j in jobs if j.status == JobStatus.RUNNING]
        terminating = [j for j in jobs if j.status == JobStatus.TERMINATING]
        assert len(running) == 1
        assert len(terminating) == 1
        assert terminating[0].termination_reason == JobTerminationReason.SCALED_DOWN

    async def test_service_zero_scale_noop(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Active service with 0 desired and no active replicas stays in current status."""
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
            status=RunStatus.RUNNING,
        )
        run.desired_replica_count = 0
        run.desired_replica_counts = json.dumps({"0": 0})
        # Create a terminated/scaled-down job to have some job history
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.SCALED_DOWN,
            replica_num=0,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        # All replicas scaled down → transitions to PENDING
        assert run.status == RunStatus.PENDING
        assert run.lock_token is None

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
            status=RunStatus.RUNNING,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.DONE,
            termination_reason=JobTerminationReason.DONE_BY_RUNNER,
        )
        lock_run(run)
        await session.commit()
        item = run_to_pipeline_item(run)
        new_lock_token = uuid.uuid4()

        from dstack._internal.server.background.pipeline_tasks.runs.active import (
            ActiveResult,
            ActiveRunUpdateMap,
        )

        async def intercept_process(context):
            # Change the lock token to simulate concurrent modification
            run.lock_token = new_lock_token
            run.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
            await session.commit()
            return ActiveResult(
                run_update_map=ActiveRunUpdateMap(
                    status=RunStatus.TERMINATING,
                    termination_reason=RunTerminationReason.ALL_JOBS_DONE,
                ),
                new_job_models=[],
                job_id_to_update_map={},
            )

        with patch(
            "dstack._internal.server.background.pipeline_tasks.runs.active.process_active_run",
            new=AsyncMock(side_effect=intercept_process),
        ):
            await worker.process(item)

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert run.lock_token == new_lock_token

    async def test_service_in_place_deployment_bump(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Service with 1 RUNNING replica at deployment_num=0, run at deployment_num=1,
        same job spec → job gets deployment_num bumped to 1."""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo Hi!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
            deployment_num=1,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            deployment_num=0,
        )
        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

        await session.refresh(job)
        assert job.deployment_num == 1

    async def test_service_rolling_deployment_scale_up(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Service with 1 out-of-date RUNNING replica whose spec differs from the new
        deployment, desired=1 → creates 1 new replica (surge), old registered replica
        untouched."""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo new!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
            deployment_num=1,
        )
        old_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            deployment_num=0,
            registered=True,
            replica_num=0,
        )
        # Make the old job's spec differ from the current run_spec so in-place bump
        # cannot be applied and rolling deployment is triggered instead.
        old_spec = get_job_spec(old_job)
        old_spec.commands = ["echo old!"]
        old_job.job_spec_data = old_spec.json()
        await session.commit()

        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

        res = await session.execute(
            select(JobModel).where(JobModel.run_id == run.id).order_by(JobModel.replica_num)
        )
        jobs = list(res.scalars().all())
        assert len(jobs) == 2
        # Old replica still RUNNING (registered, not terminated during rolling)
        assert jobs[0].status == JobStatus.RUNNING
        assert jobs[0].deployment_num == 0
        # New surge replica created
        assert jobs[1].status == JobStatus.SUBMITTED
        assert jobs[1].deployment_num == 1

    async def test_service_rolling_deployment_scale_down_old_unregistered(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Service with 1 up-to-date RUNNING+registered and 1 out-of-date RUNNING+unregistered
        replica (with a different spec) → old unregistered replica terminated."""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo new!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
            deployment_num=1,
        )
        # Up-to-date registered replica
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            deployment_num=1,
            registered=True,
            replica_num=0,
        )
        # Out-of-date unregistered replica with different spec
        old_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            deployment_num=0,
            registered=False,
            replica_num=1,
        )
        old_spec = get_job_spec(old_job)
        old_spec.commands = ["echo old!"]
        old_job.job_spec_data = old_spec.json()
        await session.commit()

        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

        await session.refresh(old_job)
        assert old_job.status == JobStatus.TERMINATING
        assert old_job.termination_reason == JobTerminationReason.SCALED_DOWN

    async def test_service_removed_group_cleanup(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        """Service run with jobs belonging to group "old" not in current config →
        those jobs get TERMINATING with SCALED_DOWN."""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        # Current config only has group "0" (default)
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="service-run",
            configuration=ServiceConfiguration(
                port=8080,
                commands=["echo Hi!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
        )
        # Active replica in current group "0"
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
        )
        # Replica belonging to a removed group "old" — manually set job_spec_data
        old_group_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=1,
        )
        # Patch the job spec to have replica_group="old"
        old_spec = get_job_spec(old_group_job)
        old_spec.replica_group = "old"
        old_group_job.job_spec_data = old_spec.json()
        await session.commit()

        lock_run(run)
        await session.commit()

        await worker.process(run_to_pipeline_item(run))

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

        await session.refresh(old_group_job)
        assert old_group_job.status == JobStatus.TERMINATING
        assert old_group_job.termination_reason == JobTerminationReason.SCALED_DOWN
