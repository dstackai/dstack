import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import (
    Profile,
    ProfileRetry,
    RetryEvent,
    StopCriteria,
)
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.background.pipeline_tasks.runs import RunWorker
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

    async def test_skips_service_run(
        self, test_db, session: AsyncSession, worker: RunWorker
    ) -> None:
        from dstack._internal.core.models.configurations import ServiceConfiguration

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
        # Service run should be skipped (no state change)
        assert run.status == RunStatus.RUNNING
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
