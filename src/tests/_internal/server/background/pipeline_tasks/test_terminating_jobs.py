import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.pipeline_tasks.terminating_jobs import (
    JobTerminatingFetcher,
    JobTerminatingPipeline,
    JobTerminatingPipelineItem,
    JobTerminatingWorker,
)
from dstack._internal.server.models import JobModel
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> JobTerminatingWorker:
    return JobTerminatingWorker(queue=Mock(), heartbeater=Mock())


@pytest.fixture
def fetcher() -> JobTerminatingFetcher:
    return JobTerminatingFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=15),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _job_to_pipeline_item(job_model: JobModel) -> JobTerminatingPipelineItem:
    assert job_model.lock_token is not None
    assert job_model.lock_expires_at is not None
    return JobTerminatingPipelineItem(
        __tablename__=job_model.__tablename__,
        id=job_model.id,
        lock_token=job_model.lock_token,
        lock_expires_at=job_model.lock_expires_at,
        prev_lock_expired=False,
        volumes_detached_at=job_model.volumes_detached_at,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock")
class TestJobTerminatingFetcher:
    async def test_fetch_selects_eligible_jobs_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: JobTerminatingFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        terminating = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=2),
        )
        past_remove_at = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=1),
        )
        past_remove_at.remove_at = stale
        past_remove_at.volumes_detached_at = stale - timedelta(seconds=30)

        future_remove_at = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale,
        )
        future_remove_at.remove_at = now + timedelta(minutes=1)

        non_terminating = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale,
        )

        recent = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=now,
        )

        locked = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale + timedelta(seconds=1),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"

        expired_same_owner = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale + timedelta(seconds=2),
        )
        expired_same_owner.lock_expires_at = stale
        expired_same_owner.lock_token = uuid.uuid4()
        expired_same_owner.lock_owner = JobTerminatingPipeline.__name__
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [
            terminating.id,
            past_remove_at.id,
            expired_same_owner.id,
        ]
        assert {(item.id, item.volumes_detached_at) for item in items} == {
            (terminating.id, None),
            (past_remove_at.id, past_remove_at.volumes_detached_at),
            (expired_same_owner.id, None),
        }

        for job in [
            terminating,
            past_remove_at,
            future_remove_at,
            non_terminating,
            recent,
            locked,
            expired_same_owner,
        ]:
            await session.refresh(job)

        fetched_jobs = [terminating, past_remove_at, expired_same_owner]
        assert all(job.lock_owner == JobTerminatingPipeline.__name__ for job in fetched_jobs)
        assert all(job.lock_expires_at is not None for job in fetched_jobs)
        assert all(job.lock_token is not None for job in fetched_jobs)
        assert len({job.lock_token for job in fetched_jobs}) == 1

        assert future_remove_at.lock_owner is None
        assert non_terminating.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_returns_oldest_jobs_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: JobTerminatingFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()

        oldest = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=now - timedelta(minutes=5),
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=now - timedelta(minutes=4),
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=now - timedelta(minutes=3),
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == JobTerminatingPipeline.__name__
        assert middle.lock_owner == JobTerminatingPipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
class TestJobTerminatingWorker:
    async def test_process_is_not_implemented(self, worker: JobTerminatingWorker):
        item = JobTerminatingPipelineItem(
            __tablename__=JobModel.__tablename__,
            id=uuid.uuid4(),
            lock_token=uuid.uuid4(),
            lock_expires_at=datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc),
            prev_lock_expired=False,
            volumes_detached_at=None,
        )

        with pytest.raises(NotImplementedError, match="not implemented yet"):
            await worker.process(item)
