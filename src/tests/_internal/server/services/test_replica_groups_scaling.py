"""Integration tests for replica groups scaling functionality"""
from typing import List

import pytest
from pydantic import parse_obj_as
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal.core.models.configurations import (
    ReplicaGroup,
    ScalingSpec,
    ServiceConfiguration,
)
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import GPUSpec, Range, ResourcesSpec
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason
from dstack._internal.server.models import RunModel
from dstack._internal.server.services.runs import scale_run_replicas
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")


async def scale_wrapper(session: AsyncSession, run: RunModel, diff: int):
    """Wrapper that handles commit and refresh like existing tests"""
    await scale_run_replicas(session, run, diff)
    await session.commit()
    await session.refresh(run)


async def make_run_with_groups(
    session: AsyncSession,
    groups_config: List[dict],  # List of {name, replicas_range, gpu, initial_jobs}
) -> RunModel:
    """Helper to create a run with replica groups"""
    project = await create_project(session=session)
    user = await create_user(session=session)
    repo = await create_repo(session=session, project_id=project.id)

    # Build replica groups
    replica_groups = []
    for group_cfg in groups_config:
        replica_groups.append(
            ReplicaGroup(
                name=group_cfg["name"],
                replicas=parse_obj_as(Range[int], group_cfg["replicas_range"]),
                resources=ResourcesSpec(
                    gpu=GPUSpec(name=[group_cfg["gpu"]], count=1)
                ),
            )
        )

    profile = Profile(name="test-profile")
    run_spec = get_run_spec(
        repo_id=repo.name,
        run_name="test-run",
        profile=profile,
        configuration=ServiceConfiguration(
            commands=["python app.py"],
            port=8000,
            replica_groups=replica_groups,
            scaling=ScalingSpec(metric="rps", target=10),
        ),
    )

    run = await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        run_name="test-run",
        run_spec=run_spec,
    )

    # Create initial jobs
    replica_num = 0
    for group_cfg in groups_config:
        for job_status in group_cfg.get("initial_jobs", []):
            job = await create_job(
                session=session,
                run=run,
                status=job_status,
                replica_num=replica_num,
                replica_group_name=group_cfg["name"],
            )
            run.jobs.append(job)
            replica_num += 1

    await session.commit()

    # Reload with jobs and project
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == run.id)
        .options(selectinload(RunModel.jobs), selectinload(RunModel.project))
    )
    return res.scalar_one()


class TestReplicaGroupsScaleDown:
    """Test scaling down with replica groups"""

    @pytest.mark.asyncio
    async def test_scale_down_only_from_autoscalable_groups(self, session: AsyncSession):
        """Test that scale down only affects autoscalable groups"""
        run = await make_run_with_groups(
            session,
            [
                {
                    "name": "fixed-h100",
                    "replicas_range": "1..1",  # Fixed
                    "gpu": "H100",
                    "initial_jobs": [JobStatus.RUNNING],
                },
                {
                    "name": "scalable-rtx",
                    "replicas_range": "1..3",  # Autoscalable
                    "gpu": "RTX5090",
                    "initial_jobs": [JobStatus.RUNNING, JobStatus.RUNNING],
                },
            ],
        )

        # Scale down by 1 (should only affect scalable group)
        await scale_wrapper(session, run, -1)

        # Check: fixed group should still have 1 running job
        fixed_jobs = [j for j in run.jobs if j.replica_group_name == "fixed-h100"]
        assert len(fixed_jobs) == 1
        assert fixed_jobs[0].status == JobStatus.RUNNING

        # Check: scalable group should have 1 terminated, 1 running
        scalable_jobs = [j for j in run.jobs if j.replica_group_name == "scalable-rtx"]
        assert len(scalable_jobs) == 2
        terminating = [j for j in scalable_jobs if j.status == JobStatus.TERMINATING]
        assert len(terminating) == 1
        assert terminating[0].termination_reason == JobTerminationReason.SCALED_DOWN

    @pytest.mark.asyncio
    async def test_scale_down_respects_group_minimums(self, session: AsyncSession):
        """Test that scale down respects each group's minimum"""
        run = await make_run_with_groups(
            session,
            [
                {
                    "name": "group-a",
                    "replicas_range": "1..3",  # Min=1
                    "gpu": "H100",
                    "initial_jobs": [JobStatus.RUNNING],  # At minimum
                },
                {
                    "name": "group-b",
                    "replicas_range": "2..5",  # Min=2
                    "gpu": "RTX5090",
                    "initial_jobs": [JobStatus.RUNNING, JobStatus.RUNNING, JobStatus.RUNNING],
                },
            ],
        )

        # Try to scale down by 2
        await scale_wrapper(session, run, -2)

        # Group A should still have 1 (at minimum)
        group_a_jobs = [j for j in run.jobs if j.replica_group_name == "group-a"]
        assert len([j for j in group_a_jobs if j.status == JobStatus.RUNNING]) == 1

        # Group B should have terminated 1 (3 -> 2, which is minimum)
        group_b_jobs = [j for j in run.jobs if j.replica_group_name == "group-b"]
        terminating = [j for j in group_b_jobs if j.status == JobStatus.TERMINATING]
        assert len(terminating) == 1

    @pytest.mark.asyncio
    async def test_scale_down_all_groups_fixed(self, session: AsyncSession):
        """Test scaling down when all groups are fixed (should not terminate anything)"""
        run = await make_run_with_groups(
            session,
            [
                {
                    "name": "fixed-1",
                    "replicas_range": "1..1",
                    "gpu": "H100",
                    "initial_jobs": [JobStatus.RUNNING],
                },
                {
                    "name": "fixed-2",
                    "replicas_range": "2..2",
                    "gpu": "RTX5090",
                    "initial_jobs": [JobStatus.RUNNING, JobStatus.RUNNING],
                },
            ],
        )

        initial_count = len(run.jobs)

        # Try to scale down
        await scale_wrapper(session, run, -1)

        # No jobs should be terminated (all groups are fixed)
        assert len(run.jobs) == initial_count
        assert all(j.status == JobStatus.RUNNING for j in run.jobs)


class TestReplicaGroupsScaleUp:
    """Test scaling up with replica groups"""

    @pytest.mark.asyncio
    async def test_scale_up_selects_autoscalable_group(self, session: AsyncSession):
        """Test that scale up only creates jobs in autoscalable groups"""
        run = await make_run_with_groups(
            session,
            [
                {
                    "name": "fixed-h100",
                    "replicas_range": "1..1",  # Fixed
                    "gpu": "H100",
                    "initial_jobs": [JobStatus.RUNNING],
                },
                {
                    "name": "scalable-rtx",
                    "replicas_range": "1..3",  # Autoscalable
                    "gpu": "RTX5090",
                    "initial_jobs": [JobStatus.RUNNING],
                },
            ],
        )

        initial_count = len(run.jobs)

        # Scale up by 1
        await scale_wrapper(session, run, 1)

        # Should have one more job
        assert len(run.jobs) == initial_count + 1

        # New job should be in scalable group
        new_jobs = [j for j in run.jobs if j.replica_num == initial_count]
        assert len(new_jobs) == 1
        assert new_jobs[0].replica_group_name == "scalable-rtx"
        assert new_jobs[0].status == JobStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_scale_up_respects_group_maximums(self, session: AsyncSession):
        """Test that scale up respects group maximums"""
        run = await make_run_with_groups(
            session,
            [
                {
                    "name": "small-group",
                    "replicas_range": "1..2",  # Max=2
                    "gpu": "H100",
                    "initial_jobs": [JobStatus.RUNNING, JobStatus.RUNNING],  # At max
                },
                {
                    "name": "large-group",
                    "replicas_range": "1..5",  # Max=5
                    "gpu": "RTX5090",
                    "initial_jobs": [JobStatus.RUNNING],
                },
            ],
        )

        # Try to scale up by 2
        await scale_wrapper(session, run, 2)

        # Small group should still have 2 (at max)
        small_jobs = [j for j in run.jobs if j.replica_group_name == "small-group"]
        assert len(small_jobs) == 2

        # Large group should have grown by 2
        large_jobs = [j for j in run.jobs if j.replica_group_name == "large-group"]
        assert len(large_jobs) == 3

    @pytest.mark.asyncio
    async def test_scale_up_no_autoscalable_groups(self, session: AsyncSession):
        """Test scale up does nothing when no autoscalable groups exist"""
        run = await make_run_with_groups(
            session,
            [
                {
                    "name": "fixed-1",
                    "replicas_range": "1..1",
                    "gpu": "H100",
                    "initial_jobs": [JobStatus.RUNNING],
                },
                {
                    "name": "fixed-2",
                    "replicas_range": "2..2",
                    "gpu": "RTX5090",
                    "initial_jobs": [JobStatus.RUNNING, JobStatus.RUNNING],
                },
            ],
        )

        initial_count = len(run.jobs)

        # Try to scale up
        await scale_wrapper(session, run, 2)

        # Should not have added any jobs
        assert len(run.jobs) == initial_count

    @pytest.mark.asyncio
    async def test_scale_up_all_groups_at_max(self, session: AsyncSession):
        """Test scale up when all autoscalable groups are at maximum"""
        run = await make_run_with_groups(
            session,
            [
                {
                    "name": "group-a",
                    "replicas_range": "1..2",
                    "gpu": "H100",
                    "initial_jobs": [JobStatus.RUNNING, JobStatus.RUNNING],  # At max
                },
                {
                    "name": "group-b",
                    "replicas_range": "1..3",
                    "gpu": "RTX5090",
                    "initial_jobs": [JobStatus.RUNNING, JobStatus.RUNNING, JobStatus.RUNNING],  # At max
                },
            ],
        )

        initial_count = len(run.jobs)

        # Try to scale up
        await scale_wrapper(session, run, 1)

        # Should not have added any jobs (all at max)
        assert len(run.jobs) == initial_count


class TestReplicaGroupsBackwardCompatibility:
    """Test backward compatibility with legacy configs"""

    @pytest.mark.asyncio
    async def test_legacy_config_scaling(self, session: AsyncSession):
        """Test scaling works with legacy replicas configuration"""
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)

        # Use legacy format (no replica_groups)
        profile = Profile(name="test-profile")
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name="test-run",
            profile=profile,
            configuration=ServiceConfiguration(
                commands=["python app.py"],
                port=8000,
                replicas=parse_obj_as(Range[int], "1..3"),  # Legacy format
                scaling=ScalingSpec(metric="rps", target=10),
            ),
        )

        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )

        # Add initial job (no group name)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
            replica_group_name=None,  # Legacy jobs have no group
        )
        run.jobs.append(job)
        await session.commit()

        # Scale up should work
        await scale_wrapper(session, run, 1)

        # Should have 2 jobs now
        assert len(run.jobs) == 2

        # New job should have "default" group name or None
        new_job = [j for j in run.jobs if j.replica_num == 1][0]
        assert new_job.replica_group_name in [None, "default"]

