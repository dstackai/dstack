import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.profiles import Profile, ProfileRetry, RetryEvent
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason, RunStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import UserModel
from dstack._internal.server.services import runs as runs_services
from dstack._internal.server.services.jobs import check_can_attach_job_volumes
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
    get_volume,
)


class TestListUserRuns:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize("include_jobs", [True, False])
    async def test_limited_list_materializes_only_latest_and_status_jobs(
        self,
        test_db,
        session: AsyncSession,
        include_jobs: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(
                name="default",
                retry=ProfileRetry(duration=3600, on_events=[RetryEvent.NO_CAPACITY]),
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.PENDING,
            run_spec=run_spec,
        )
        await create_job(
            session=session,
            run=run,
            submission_num=0,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )
        for submission_num in range(1, 12):
            await create_job(
                session=session,
                run=run,
                submission_num=submission_num,
                status=JobStatus.SUBMITTED,
            )

        user_id = user.id
        project_name = project.name
        session.expunge_all()
        user = (
            await session.execute(select(UserModel).where(UserModel.id == user_id))
        ).scalar_one()
        loaded_job_submission_nums = []
        unbounded_job_selects = []
        original_list_jobs = runs_services._list_jobs_for_runs_list

        async def list_jobs_wrapper(*args, **kwargs):
            jobs = await original_list_jobs(*args, **kwargs)
            loaded_job_submission_nums.append(sorted(job.submission_num for job in jobs))
            return jobs

        monkeypatch.setattr(runs_services, "_list_jobs_for_runs_list", list_jobs_wrapper)

        @event.listens_for(test_db.engine.sync_engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            normalized_statement = statement.lower()
            if "from jobs" in normalized_statement and "row_number" not in normalized_statement:
                unbounded_job_selects.append(statement)

        try:
            runs = await runs_services.list_user_runs(
                session=session,
                user=user,
                project_name=project_name,
                repo_id=None,
                username=None,
                only_active=False,
                include_jobs=include_jobs,
                job_submissions_limit=1,
                prev_submitted_at=None,
                prev_run_id=None,
                limit=100,
                ascending=False,
            )
        finally:
            event.remove(
                test_db.engine.sync_engine, "before_cursor_execute", before_cursor_execute
            )

        assert len(runs) == 1
        assert runs[0].status_message == "retrying"
        if include_jobs:
            assert len(runs[0].jobs) == 1
            assert [s.submission_num for s in runs[0].jobs[0].job_submissions] == [11]
            assert runs[0].latest_job_submission is not None
            assert runs[0].latest_job_submission.submission_num == 11
        else:
            assert runs[0].jobs == []
            assert runs[0].latest_job_submission is None

        assert loaded_job_submission_nums == [[0, 11]]
        assert unbounded_job_selects == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        ("include_jobs", "job_submissions_limit"),
        [
            (True, 1),
            (True, 0),
            (True, None),
            (False, 1),
        ],
    )
    async def test_limited_list_preserves_status_message_matrix(
        self,
        test_db,
        session: AsyncSession,
        include_jobs: bool,
        job_submissions_limit: int | None,
    ) -> None:
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        retry_profile = Profile(
            name="default",
            retry=ProfileRetry(duration=3600, on_events=[RetryEvent.NO_CAPACITY]),
        )
        no_retry_profile = Profile(name="default")

        async def create_listed_run(
            name: str,
            status: RunStatus,
            profile: Profile = no_retry_profile,
        ):
            run_spec = get_run_spec(repo_id=repo.name, run_name=name, profile=profile)
            return await create_run(
                session=session,
                project=project,
                repo=repo,
                user=user,
                run_name=name,
                status=status,
                run_spec=run_spec,
            )

        await create_listed_run("no-jobs", RunStatus.SUBMITTED)

        all_pulling = await create_listed_run("all-pulling", RunStatus.PROVISIONING)
        await create_job(
            session=session,
            run=all_pulling,
            job_num=0,
            submission_num=0,
            status=JobStatus.DONE,
        )
        await create_job(
            session=session,
            run=all_pulling,
            job_num=0,
            submission_num=1,
            status=JobStatus.PULLING,
        )
        await create_job(
            session=session,
            run=all_pulling,
            job_num=1,
            submission_num=0,
            status=JobStatus.PULLING,
        )

        some_pulling = await create_listed_run("some-pulling", RunStatus.PROVISIONING)
        await create_job(
            session=session,
            run=some_pulling,
            job_num=0,
            submission_num=0,
            status=JobStatus.PULLING,
        )
        await create_job(
            session=session,
            run=some_pulling,
            job_num=1,
            submission_num=0,
            status=JobStatus.RUNNING,
        )

        retrying = await create_listed_run(
            "retrying",
            RunStatus.PENDING,
            profile=retry_profile,
        )
        await create_job(
            session=session,
            run=retrying,
            submission_num=0,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )
        await create_job(
            session=session,
            run=retrying,
            submission_num=1,
            status=JobStatus.SUBMITTED,
        )

        no_retry = await create_listed_run("no-retry", RunStatus.PENDING)
        await create_job(
            session=session,
            run=no_retry,
            submission_num=0,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )
        await create_job(
            session=session,
            run=no_retry,
            submission_num=1,
            status=JobStatus.SUBMITTED,
        )

        newer_termination = await create_listed_run(
            "newer-termination",
            RunStatus.PENDING,
            profile=retry_profile,
        )
        await create_job(
            session=session,
            run=newer_termination,
            submission_num=0,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )
        await create_job(
            session=session,
            run=newer_termination,
            submission_num=1,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
        )
        await create_job(
            session=session,
            run=newer_termination,
            submission_num=2,
            status=JobStatus.SUBMITTED,
        )

        finished_failed = await create_listed_run(
            "finished-failed",
            RunStatus.FAILED,
            profile=retry_profile,
        )
        await create_job(
            session=session,
            run=finished_failed,
            submission_num=0,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )

        user_id = user.id
        project_name = project.name
        session.expunge_all()
        user = (
            await session.execute(select(UserModel).where(UserModel.id == user_id))
        ).scalar_one()

        runs = await runs_services.list_user_runs(
            session=session,
            user=user,
            project_name=project_name,
            repo_id=None,
            username=None,
            only_active=False,
            include_jobs=include_jobs,
            job_submissions_limit=job_submissions_limit,
            prev_submitted_at=None,
            prev_run_id=None,
            limit=100,
            ascending=False,
        )
        status_messages = {run.run_spec.run_name: run.status_message for run in runs}

        assert status_messages == {
            "no-jobs": "submitted",
            "all-pulling": "pulling",
            "some-pulling": "provisioning",
            "retrying": "retrying",
            "no-retry": "pending",
            "newer-termination": "pending",
            "finished-failed": "failed",
        }
        if include_jobs and job_submissions_limit == 0:
            assert all(len(job.job_submissions) == 0 for run in runs for job in run.jobs)
        if not include_jobs:
            assert all(run.jobs == [] for run in runs)


class TestCanAttachRunVolumes:
    @pytest.mark.asyncio
    async def test_can_attach(self):
        vol11 = get_volume(name="vol11")
        vol11.configuration.backend = BackendType.AWS
        vol11.configuration.region = "eu-west-1"
        vol12 = get_volume(name="vol12")
        vol12.configuration.backend = BackendType.AWS
        vol12.configuration.region = "eu-west-2"
        vol21 = get_volume(name="vol21")
        vol21.configuration.backend = BackendType.AWS
        vol21.configuration.region = "eu-west-1"
        vol22 = get_volume(name="vol22")
        vol22.configuration.backend = BackendType.AWS
        vol22.configuration.region = "eu-west-2"
        volumes = [[vol11, vol12], [vol21, vol22]]
        check_can_attach_job_volumes(volumes)

    @pytest.mark.asyncio
    async def test_cannot_attach_different_mount_points_with_different_backends_regions(self):
        vol1 = get_volume(name="vol11")
        vol1.configuration.backend = BackendType.AWS
        vol1.configuration.region = "eu-west-1"
        vol2 = get_volume(name="vol12")
        vol2.configuration.backend = BackendType.AWS
        vol2.configuration.region = "eu-west-2"
        volumes = [[vol1], [vol2]]
        with pytest.raises(ServerClientError):
            check_can_attach_job_volumes(volumes)

    @pytest.mark.asyncio
    async def test_cannot_attach_same_volume_at_different_mount_points(self):
        vol1 = get_volume(name="vol11")
        vol1.configuration.backend = BackendType.AWS
        vol1.configuration.region = "eu-west-1"
        volumes = [[vol1], [vol1]]
        with pytest.raises(ServerClientError):
            check_can_attach_job_volumes(volumes)
