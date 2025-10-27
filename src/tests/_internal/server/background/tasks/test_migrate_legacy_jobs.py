"""
Tests for migrating legacy jobs without replica_group_name.
"""

import pytest

from dstack._internal.core.models.configurations import (
    ServiceConfiguration,
)
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Range, ResourcesSpec
from dstack._internal.core.models.runs import JobStatus, RunSpec
from dstack._internal.server.background.tasks.process_runs import (
    _migrate_legacy_job_replica_groups,
)
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)


class TestMigrateLegacyJobs:
    @pytest.mark.asyncio
    async def test_migrates_jobs_without_replica_group_name(
        self, test_db, session, socket_enabled
    ):
        """Test that jobs without replica_group_name get migrated correctly."""
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)

        # Create a run with replica_groups configuration
        service_config = ServiceConfiguration(
            replica_groups=[
                {
                    "name": "h100-gpu",
                    "replicas": Range(min=1, max=1),
                    "resources": ResourcesSpec(gpu="H100:1"),
                },
                {
                    "name": "rtx5090-gpu",
                    "replicas": Range(min=1, max=1),
                    "resources": ResourcesSpec(gpu="RTX5090:1"),
                },
            ],
            commands=["echo hello"],
            port=8000,
        )

        run_spec = RunSpec(
            run_name="test-service",
            repo_id="test-repo",
            configuration=service_config,
            merged_profile=Profile(),
        )

        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-service",
            run_spec=run_spec,
        )

        # Create jobs WITHOUT replica_group_name (simulating old code)
        job1 = await create_job(
            session=session,
            run=run,
            replica_num=0,
            replica_group_name=None,  # Old job without group
            status=JobStatus.RUNNING,
        )

        job2 = await create_job(
            session=session,
            run=run,
            replica_num=1,
            replica_group_name=None,  # Old job without group
            status=JobStatus.RUNNING,
        )

        # Verify jobs have no group
        assert job1.replica_group_name is None
        assert job2.replica_group_name is None

        # Refresh run to load jobs relationship
        await session.refresh(run, ["jobs"])

        # Run migration
        await _migrate_legacy_job_replica_groups(session, run)
        await session.refresh(job1)
        await session.refresh(job2)

        # Verify jobs now have correct groups
        assert job1.replica_group_name == "h100-gpu"
        assert job2.replica_group_name == "rtx5090-gpu"

    @pytest.mark.asyncio
    async def test_skips_already_migrated_jobs(self, test_db, session):
        """Test that jobs with replica_group_name are not re-migrated."""
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)

        service_config = ServiceConfiguration(
            replica_groups=[
                {
                    "name": "gpu-group",
                    "replicas": Range(min=1, max=1),
                    "resources": ResourcesSpec(gpu="A100:1"),
                },
            ],
            commands=["echo hello"],
            port=8000,
        )

        run_spec = RunSpec(
            run_name="test-service",
            repo_id="test-repo",
            configuration=service_config,
            merged_profile=Profile(),
        )

        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-service",
            run_spec=run_spec,
        )

        # Create job WITH replica_group_name (already migrated)
        job = await create_job(
            session=session,
            run=run,
            replica_num=0,
            replica_group_name="gpu-group",
            status=JobStatus.RUNNING,
        )

        original_group = job.replica_group_name

        # Run migration (should be a no-op)
        await _migrate_legacy_job_replica_groups(session, run)
        await session.refresh(job)

        # Verify group unchanged
        assert job.replica_group_name == original_group

    @pytest.mark.asyncio
    async def test_skips_non_service_runs(self, test_db, session):
        """Test that non-service runs are skipped."""
        from dstack._internal.core.models.configurations import TaskConfiguration

        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)

        task_config = TaskConfiguration(
            commands=["echo hello"],
        )

        run_spec = RunSpec(
            run_name="test-task",
            repo_id="test-repo",
            configuration=task_config,
            merged_profile=Profile(),
        )

        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-task",
            run_spec=run_spec,
        )

        job = await create_job(
            session=session,
            run=run,
            replica_num=0,
            replica_group_name=None,
            status=JobStatus.RUNNING,
        )

        # Run migration (should skip task runs)
        await _migrate_legacy_job_replica_groups(session, run)
        await session.refresh(job)

        # Verify no change
        assert job.replica_group_name is None

    @pytest.mark.asyncio
    async def test_skips_legacy_replicas_config(self, test_db, session):
        """Test that runs using legacy 'replicas' (not replica_groups) are skipped."""
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)

        # Use legacy replicas configuration
        service_config = ServiceConfiguration(
            replicas=Range(min=2, max=2),
            commands=["echo hello"],
            port=8000,
        )

        run_spec = RunSpec(
            run_name="test-service",
            repo_id="test-repo",
            configuration=service_config,
            merged_profile=Profile(),
        )

        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-service",
            run_spec=run_spec,
        )

        job = await create_job(
            session=session,
            run=run,
            replica_num=0,
            replica_group_name=None,
            status=JobStatus.RUNNING,
        )

        # Run migration (should skip legacy replicas)
        await _migrate_legacy_job_replica_groups(session, run)
        await session.refresh(job)

        # Verify no change (legacy replicas don't use replica_group_name)
        assert job.replica_group_name is None
