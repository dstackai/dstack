import datetime
from typing import Union
from unittest.mock import patch

import pytest
from pydantic import parse_obj_as
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.background.tasks.process_runs as process_runs
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.models import RunModel
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_pool,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_run_spec,
)


async def make_run(
    session: AsyncSession, status: RunStatus = RunStatus.SUBMITTED, replicas: Union[str, int] = 1
) -> RunModel:
    project = await create_project(session=session)
    user = await create_user(session=session)
    repo = await create_repo(
        session=session,
        project_id=project.id,
    )
    project.default_pool = await create_pool(
        session=session, project=project, pool_name="default-pool"
    )
    run_name = "test-run"
    profile = Profile(
        name="test-profile",
        retry=True,
    )
    run_spec = get_run_spec(
        repo_id=repo.name,
        run_name=run_name,
        profile=profile,
        configuration=ServiceConfiguration(
            commands=["echo hello"],
            port=8000,
            replicas=parse_obj_as(Range[int], replicas),
        ),
    )
    return await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        run_name=run_name,
        run_spec=run_spec,
        status=status,
    )


class TestProcessRuns:
    @pytest.mark.asyncio
    async def test_submitted_to_provisioning(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.SUBMITTED)
        await create_job(session=session, run=run, status=JobStatus.PROVISIONING)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_provisioning_to_running(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PROVISIONING)
        await create_job(session=session, run=run, status=JobStatus.RUNNING)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

    @pytest.mark.asyncio
    async def test_keep_provisioning(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PROVISIONING)
        await create_job(session=session, run=run, status=JobStatus.PULLING)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_running_to_done(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING)
        await create_job(session=session, run=run, status=JobStatus.DONE)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.ALL_JOBS_DONE

    @pytest.mark.asyncio
    async def test_terminate_run_jobs(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.TERMINATING)
        run.termination_reason = RunTerminationReason.JOB_FAILED
        job = await create_job(
            session=session,
            run=run,
            job_provisioning_data=get_job_provisioning_data(),
            status=JobStatus.RUNNING,
        )

        with patch("dstack._internal.server.services.jobs._stop_runner") as stop_runner:
            await process_runs.process_single_run(run.id, [])
            stop_runner.assert_called_once()
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING

    @pytest.mark.asyncio
    async def test_retry_running_to_pending(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING)
        instance = await create_instance(
            session, project=run.project, pool=run.project.default_pool, spot=True
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            submitted_at=run.submitted_at,
            last_processed_at=run.submitted_at,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            instance=instance,
            job_provisioning_data=get_job_provisioning_data(),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.PENDING

    @pytest.mark.asyncio
    async def test_retry_running_to_failed(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING)
        instance = await create_instance(
            session, project=run.project, pool=run.project.default_pool, spot=True
        )
        # job exited with non-zero code
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=None,
            instance=instance,
        )

        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.JOB_FAILED

    @pytest.mark.asyncio
    async def test_pending_to_submitted(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PENDING)
        await create_job(session=session, run=run, status=JobStatus.FAILED)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert len(run.jobs) == 2
        assert run.jobs[0].status == JobStatus.FAILED
        assert run.jobs[1].status == JobStatus.SUBMITTED


class TestProcessRunsReplicas:
    @pytest.mark.asyncio
    async def test_submitted_to_provisioning_if_any(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.SUBMITTED, replicas=2)
        await create_job(session=session, run=run, status=JobStatus.SUBMITTED, replica_num=0)
        await create_job(session=session, run=run, status=JobStatus.PROVISIONING, replica_num=1)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_provisioning_to_running_if_any(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PROVISIONING, replicas=2)
        await create_job(session=session, run=run, status=JobStatus.RUNNING, replica_num=0)
        await create_job(session=session, run=run, status=JobStatus.PROVISIONING, replica_num=1)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

    @pytest.mark.asyncio
    async def test_all_no_capacity_to_pending(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            submitted_at=run.submitted_at,
            last_processed_at=run.submitted_at,
            replica_num=0,
            instance=await create_instance(
                session, project=run.project, pool=run.project.default_pool, spot=True
            ),
            job_provisioning_data=get_job_provisioning_data(),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            submitted_at=run.submitted_at,
            last_processed_at=run.submitted_at,
            replica_num=1,
            instance=await create_instance(
                session, project=run.project, pool=run.project.default_pool, spot=True
            ),
            job_provisioning_data=get_job_provisioning_data(),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.PENDING

    @pytest.mark.asyncio
    async def test_some_no_capacity_keep_running(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            submitted_at=run.submitted_at,
            last_processed_at=run.last_processed_at,
            replica_num=0,
            instance=await create_instance(
                session, project=run.project, pool=run.project.default_pool, spot=True
            ),
            job_provisioning_data=get_job_provisioning_data(),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            submitted_at=run.submitted_at,
            last_processed_at=run.last_processed_at,
            replica_num=1,
            job_provisioning_data=get_job_provisioning_data(),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 3
        assert run.jobs[2].status == JobStatus.SUBMITTED
        assert run.jobs[2].replica_num == 0

    @pytest.mark.asyncio
    async def test_some_failed_to_terminating(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
            replica_num=0,
        )
        await create_job(session=session, run=run, status=JobStatus.RUNNING, replica_num=1)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.JOB_FAILED

    @pytest.mark.asyncio
    async def test_pending_to_submitted_adds_replicas(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PENDING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            replica_num=0,
        )

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert len(run.jobs) == 3
        assert run.jobs[1].status == JobStatus.SUBMITTED
        assert run.jobs[1].replica_num == 0
        assert run.jobs[2].status == JobStatus.SUBMITTED
        assert run.jobs[2].replica_num == 1


# TODO(egor-s): TestProcessRunsMultiNode
# TODO(egor-s): TestProcessRunsAutoScaling
