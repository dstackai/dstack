import asyncio
import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.pipeline_tasks.jobs_submitted import (
    JobSubmittedFetcher,
    JobSubmittedPipeline,
    JobSubmittedPipelineItem,
    JobSubmittedWorker,
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

pytestmark = pytest.mark.usefixtures("image_config_mock")


@pytest.fixture
def fetcher() -> JobSubmittedFetcher:
    return JobSubmittedFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=4),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


@pytest.fixture
def worker() -> JobSubmittedWorker:
    return JobSubmittedWorker(queue=Mock(), heartbeater=Mock())


def _lock_job_foreign(job_model: JobModel) -> None:
    job_model.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = "OtherPipeline"


def _lock_job_expired_same_owner(job_model: JobModel) -> None:
    job_model.lock_expires_at = get_current_datetime() - timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = JobSubmittedPipeline.__name__


def _job_to_pipeline_item(job_model: JobModel) -> JobSubmittedPipelineItem:
    assert job_model.lock_token is not None
    assert job_model.lock_expires_at is not None
    return JobSubmittedPipelineItem(
        __tablename__=job_model.__tablename__,
        id=job_model.id,
        lock_expires_at=job_model.lock_expires_at,
        lock_token=job_model.lock_token,
        prev_lock_expired=False,
        instance_assigned=job_model.instance_assigned,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestJobSubmittedFetcher:
    async def test_fetch_selects_eligible_jobs_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: JobSubmittedFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        assignment_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=1),
            last_processed_at=stale - timedelta(seconds=2),
            instance_assigned=False,
        )
        provisioning_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=1),
            instance_assigned=True,
            job_num=1,
        )
        fresh_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=now,
            last_processed_at=now,
            job_num=2,
        )
        waiting_master = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=3),
            last_processed_at=stale - timedelta(seconds=3),
            waiting_master_job=True,
            job_num=3,
        )
        recent_retry = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=4),
            last_processed_at=now - timedelta(seconds=1),
            job_num=4,
        )
        foreign_locked = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=5),
            last_processed_at=stale - timedelta(seconds=4),
            job_num=5,
        )
        _lock_job_foreign(foreign_locked)
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [
            assignment_job.id,
            provisioning_job.id,
            fresh_job.id,
        ]
        assert [(item.id, item.instance_assigned) for item in items] == [
            (assignment_job.id, False),
            (provisioning_job.id, True),
            (fresh_job.id, False),
        ]

        for job in [
            assignment_job,
            provisioning_job,
            fresh_job,
            waiting_master,
            recent_retry,
            foreign_locked,
        ]:
            await session.refresh(job)

        fetched_jobs = [assignment_job, provisioning_job, fresh_job]
        assert all(job.lock_owner == JobSubmittedPipeline.__name__ for job in fetched_jobs)
        assert all(job.lock_expires_at is not None for job in fetched_jobs)
        assert all(job.lock_token is not None for job in fetched_jobs)
        assert len({job.lock_token for job in fetched_jobs}) == 1

        assert waiting_master.lock_owner is None
        assert recent_retry.lock_owner is None
        assert foreign_locked.lock_owner == "OtherPipeline"

    async def test_fetch_orders_by_priority_then_last_processed_at(
        self, test_db, session: AsyncSession, fetcher: JobSubmittedFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        now = get_current_datetime()

        low_priority_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="low-priority-run",
            priority=1,
        )
        high_priority_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="high-priority-run",
            priority=10,
        )

        low_priority_job = await create_job(
            session=session,
            run=low_priority_run,
            submitted_at=now - timedelta(minutes=3),
            last_processed_at=now - timedelta(minutes=2),
        )
        newer_high_priority_job = await create_job(
            session=session,
            run=high_priority_run,
            submitted_at=now - timedelta(minutes=4),
            last_processed_at=now - timedelta(minutes=1),
        )
        older_high_priority_job = await create_job(
            session=session,
            run=high_priority_run,
            submitted_at=now - timedelta(minutes=5),
            last_processed_at=now - timedelta(minutes=2, seconds=30),
            job_num=1,
        )

        items = await fetcher.fetch(limit=3)

        assert [item.id for item in items] == [
            older_high_priority_job.id,
            newer_high_priority_job.id,
            low_priority_job.id,
        ]

    async def test_fetch_retries_expired_same_owner_lock_and_respects_limit(
        self, test_db, session: AsyncSession, fetcher: JobSubmittedFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        oldest = await create_job(
            session=session,
            run=run,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=2),
        )
        expired_same_owner = await create_job(
            session=session,
            run=run,
            submitted_at=stale - timedelta(minutes=1),
            last_processed_at=stale - timedelta(seconds=1),
            job_num=1,
        )
        newest = await create_job(
            session=session,
            run=run,
            submitted_at=stale,
            last_processed_at=stale,
            job_num=2,
        )
        _lock_job_expired_same_owner(expired_same_owner)
        await session.commit()

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, expired_same_owner.id]

        await session.refresh(expired_same_owner)
        assert expired_same_owner.lock_owner == JobSubmittedPipeline.__name__
        assert expired_same_owner.lock_token is not None
        assert expired_same_owner.lock_expires_at is not None

        await session.refresh(newest)
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestJobSubmittedWorker:
    async def test_process_is_placeholder_noop(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run)
        job.lock_token = uuid.uuid4()
        job.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
        job.lock_owner = JobSubmittedPipeline.__name__
        await session.commit()

        item = _job_to_pipeline_item(job)

        await worker.process(item)

        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert job.lock_owner == JobSubmittedPipeline.__name__
