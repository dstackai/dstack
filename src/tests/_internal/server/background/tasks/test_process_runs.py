import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.background.tasks.process_runs as process_runs
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.models import RunModel
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)


@pytest_asyncio.fixture
async def run(session: AsyncSession) -> RunModel:
    project = await create_project(session=session)
    user = await create_user(session=session)
    repo = await create_repo(
        session=session,
        project_id=project.id,
    )
    return await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
    )


class TestProcessRuns:
    @pytest.mark.asyncio
    async def test_submitted_to_starting(self, test_db, session: AsyncSession, run: RunModel):
        run.status = JobStatus.SUBMITTED
        await create_job(session=session, run=run, status=JobStatus.PROVISIONING)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_starting_to_running(self, test_db, session: AsyncSession, run: RunModel):
        run.status = JobStatus.PROVISIONING
        await create_job(session=session, run=run, status=JobStatus.RUNNING)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == JobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_keep_starting(self, test_db, session: AsyncSession, run: RunModel):
        run.status = JobStatus.PROVISIONING
        await create_job(session=session, run=run, status=JobStatus.PULLING)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_running_to_done(self, test_db, session: AsyncSession, run: RunModel):
        run.status = JobStatus.RUNNING
        await create_job(session=session, run=run, status=JobStatus.DONE)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(run)
        assert run.status == JobStatus.DONE

    @pytest.mark.asyncio
    async def test_terminate_run_jobs(self, test_db, session: AsyncSession, run: RunModel):
        run.status = JobStatus.TERMINATED
        # TODO(egor-s): set run.processing_finished
        job = await create_job(session=session, run=run, status=JobStatus.RUNNING)

        await process_runs.process_single_run(run.id, [])
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATED
        # TODO(egor-s): assert job.error_code
        # await session.refresh(run)
        # TODO(egor-s): assert run.processing_finished is True

    # TODO(egor-s): test_running_to_pending
    # TODO(egor-s): test_running_to_failed
    # TODO(egor-s): test_running_to_terminated


# TODO(egor-s): TestProcessRunsMultiNode
# TODO(egor-s): TestProcessRunsReplicas
# TODO(egor-s): TestProcessRunsAutoScaling
