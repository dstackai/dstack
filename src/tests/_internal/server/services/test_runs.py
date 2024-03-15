from typing import List

import pytest
from pydantic import parse_obj_as
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerError
from dstack._internal.core.models.configurations import ScalingSpec, ServiceConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason, RunStatus
from dstack._internal.server.models import RunModel
from dstack._internal.server.services.runs import scale_run_replicas
from dstack._internal.server.testing.common import (
    create_job,
    create_pool,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
)


async def make_run(
    session: AsyncSession,
    replicas_statuses: List[JobStatus],
    status: RunStatus = RunStatus.RUNNING,
    replicas: str = 1,
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
    profile = Profile(name="test-profile")
    run_spec = get_run_spec(
        repo_id=repo.name,
        run_name=run_name,
        profile=profile,
        configuration=ServiceConfiguration(
            commands=["echo hello"],
            port=8000,
            replicas=parse_obj_as(Range[int], replicas),
            scaling=ScalingSpec(
                metric="rps",
                target=1,
            ),
        ),
    )
    run = await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        run_name=run_name,
        run_spec=run_spec,
        status=status,
    )
    for replica_num, job_status in enumerate(replicas_statuses):
        await create_job(
            session=session,
            run=run,
            status=job_status,
            replica_num=replica_num,
        )
    await session.refresh(run)
    return run


async def scale_wrapper(session: AsyncSession, run: RunModel, diff: int):
    await scale_run_replicas(session, run, diff)
    await session.commit()
    await session.refresh(run)


class TestScaleRunReplicas:
    @pytest.mark.asyncio
    async def test_no_scale(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.RUNNING,
            ],
            replicas="0..1",
        )
        await scale_wrapper(session, run, 0)
        assert len(run.jobs) == 1

    @pytest.mark.asyncio
    async def test_downscale_to_zero(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.RUNNING,
            ],
            replicas="0..1",
        )
        await scale_wrapper(session, run, -1)
        assert len(run.jobs) == 1
        assert run.jobs[0].status == JobStatus.TERMINATING
        assert run.jobs[0].termination_reason == JobTerminationReason.SCALED_DOWN

    @pytest.mark.asyncio
    async def test_upscale_new(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.RUNNING,
            ],
            replicas="0..2",
        )
        await scale_wrapper(session, run, 1)
        assert len(run.jobs) == 2
        assert run.jobs[1].status == JobStatus.SUBMITTED
        assert run.jobs[1].replica_num == 1

    @pytest.mark.asyncio
    async def test_upscale_terminated(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.RUNNING,
                JobStatus.TERMINATED,
            ],
            replicas="0..2",
        )
        await scale_wrapper(session, run, 1)
        assert len(run.jobs) == 3
        assert run.jobs[0].status == JobStatus.RUNNING
        assert run.jobs[1].status == JobStatus.TERMINATED
        assert run.jobs[2].status == JobStatus.SUBMITTED
        assert run.jobs[2].replica_num == 1

    @pytest.mark.asyncio
    async def test_downscale_less_important(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.PROVISIONING,
                JobStatus.RUNNING,
            ],
            replicas="0..2",
        )
        await scale_wrapper(session, run, -1)
        assert len(run.jobs) == 2
        assert run.jobs[0].status == JobStatus.TERMINATING
        assert run.jobs[0].termination_reason == JobTerminationReason.SCALED_DOWN
        assert run.jobs[1].status == JobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_downscale_greater_replica_num(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.RUNNING,
                JobStatus.RUNNING,
            ],
            replicas="0..2",
        )
        await scale_wrapper(session, run, -1)
        assert len(run.jobs) == 2
        assert run.jobs[0].status == JobStatus.RUNNING
        assert run.jobs[1].status == JobStatus.TERMINATING
        assert run.jobs[1].termination_reason == JobTerminationReason.SCALED_DOWN

    @pytest.mark.asyncio
    async def test_no_downscale_below_limit(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.RUNNING,
            ],
            replicas="1..2",
        )
        with pytest.raises(ServerError):
            await scale_wrapper(session, run, -1)

    @pytest.mark.asyncio
    async def test_no_upscale_above_limit(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.RUNNING,
            ],
            replicas="0..1",
        )
        with pytest.raises(ServerError):
            await scale_wrapper(session, run, 1)

    @pytest.mark.asyncio
    async def test_upscale_mixed(self, test_db, session: AsyncSession):
        run = await make_run(
            session,
            [
                JobStatus.TERMINATED,
            ],
            replicas="0..2",
        )
        await scale_wrapper(session, run, 2)
        assert len(run.jobs) == 3
        assert run.jobs[0].status == JobStatus.TERMINATED
        assert run.jobs[1].status == JobStatus.SUBMITTED
        assert run.jobs[1].replica_num == 0
        assert run.jobs[2].status == JobStatus.SUBMITTED
        assert run.jobs[2].replica_num == 1
