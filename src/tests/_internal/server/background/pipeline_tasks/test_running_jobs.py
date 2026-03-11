import asyncio
import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.server.background.pipeline_tasks.jobs_running import (
    JobRunningFetcher,
    JobRunningPipeline,
)
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)
from dstack._internal.utils.common import get_current_datetime

pytestmark = pytest.mark.usefixtures("image_config_mock")


@pytest.fixture
def fetcher() -> JobRunningFetcher:
    return JobRunningFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=10),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _lock_job_foreign(job_model):
    job_model.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = "OtherPipeline"


def _lock_job_expired_same_owner(job_model):
    job_model.lock_expires_at = get_current_datetime() - timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = JobRunningPipeline.__name__


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestJobRunningFetcher:
    async def test_fetch_selects_eligible_jobs_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        provisioning = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            last_processed_at=stale - timedelta(seconds=4),
        )
        pulling = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            last_processed_at=stale - timedelta(seconds=3),
        )
        running = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=2),
        )
        expired_same_owner = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=1),
        )
        _lock_job_expired_same_owner(expired_same_owner)

        recent = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=now,
        )
        foreign_locked = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=stale,
        )
        _lock_job_foreign(foreign_locked)
        finished = await create_job(
            session=session,
            run=run,
            status=JobStatus.DONE,
            last_processed_at=stale - timedelta(seconds=5),
        )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [
            provisioning.id,
            pulling.id,
            running.id,
            expired_same_owner.id,
        ]
        assert [item.status for item in items] == [
            JobStatus.PROVISIONING,
            JobStatus.PULLING,
            JobStatus.RUNNING,
            JobStatus.RUNNING,
        ]

        for job in [
            provisioning,
            pulling,
            running,
            expired_same_owner,
            recent,
            foreign_locked,
            finished,
        ]:
            await session.refresh(job)

        fetched_jobs = [provisioning, pulling, running, expired_same_owner]
        assert all(job.lock_owner == JobRunningPipeline.__name__ for job in fetched_jobs)
        assert all(job.lock_expires_at is not None for job in fetched_jobs)
        assert all(job.lock_token is not None for job in fetched_jobs)
        assert len({job.lock_token for job in fetched_jobs}) == 1

        assert recent.lock_owner is None
        assert foreign_locked.lock_owner == "OtherPipeline"
        assert finished.lock_owner is None

    async def test_fetch_excludes_jobs_from_terminating_runs(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        active_run = await create_run(session=session, project=project, repo=repo, user=user)
        terminating_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="terminating-run",
            status=RunStatus.TERMINATING,
        )
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        active_job = await create_job(
            session=session,
            run=active_run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=1),
        )
        terminating_run_job = await create_job(
            session=session,
            run=terminating_run,
            status=JobStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=2),
        )

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [active_job.id]

        await session.refresh(active_job)
        await session.refresh(terminating_run_job)

        assert active_job.lock_owner == JobRunningPipeline.__name__
        assert terminating_run_job.lock_owner is None

    async def test_fetch_returns_oldest_jobs_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: JobRunningFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()

        oldest = await create_job(
            session=session,
            run=run,
            status=JobStatus.PROVISIONING,
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_job(
            session=session,
            run=run,
            status=JobStatus.PULLING,
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == JobRunningPipeline.__name__
        assert middle.lock_owner == JobRunningPipeline.__name__
        assert newest.lock_owner is None
