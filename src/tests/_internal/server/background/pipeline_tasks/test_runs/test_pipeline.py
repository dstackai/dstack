import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import RunStatus
from dstack._internal.server.background.pipeline_tasks.runs import (
    RunFetcher,
    RunPipeline,
)
from dstack._internal.server.testing.common import (
    create_project,
    create_repo,
    create_run,
    create_user,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestRunFetcher:
    async def test_fetch_selects_eligible_runs_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: RunFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        now = get_current_datetime()
        stale = now - dt.timedelta(minutes=1)

        submitted = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="submitted",
            status=RunStatus.SUBMITTED,
            submitted_at=stale - dt.timedelta(seconds=5),
        )
        running = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="running",
            status=RunStatus.RUNNING,
            submitted_at=stale - dt.timedelta(seconds=4),
        )
        pending_retry = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="pending-retry",
            status=RunStatus.PENDING,
            submitted_at=stale - dt.timedelta(seconds=3),
            resubmission_attempt=1,
        )
        pending_scheduled_ready = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="pending-scheduled-ready",
            status=RunStatus.PENDING,
            submitted_at=stale - dt.timedelta(seconds=2),
            next_triggered_at=stale,
        )
        pending_zero_scaled = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="pending-zero-scaled",
            status=RunStatus.PENDING,
            submitted_at=stale - dt.timedelta(seconds=1),
        )
        future_scheduled = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="future-scheduled",
            status=RunStatus.PENDING,
            submitted_at=stale,
            next_triggered_at=now + dt.timedelta(minutes=1),
        )
        finished = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="finished",
            status=RunStatus.DONE,
            submitted_at=stale + dt.timedelta(seconds=1),
        )
        recent = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="recent",
            status=RunStatus.RUNNING,
            submitted_at=now,
            last_processed_at=now + dt.timedelta(seconds=10),
        )

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {
            submitted.id,
            running.id,
            pending_retry.id,
            pending_scheduled_ready.id,
            pending_zero_scaled.id,
        }
        assert {item.id: item.status for item in items} == {
            submitted.id: RunStatus.SUBMITTED,
            running.id: RunStatus.RUNNING,
            pending_retry.id: RunStatus.PENDING,
            pending_scheduled_ready.id: RunStatus.PENDING,
            pending_zero_scaled.id: RunStatus.PENDING,
        }

        for run in [
            submitted,
            running,
            pending_retry,
            pending_scheduled_ready,
            pending_zero_scaled,
            future_scheduled,
            finished,
            recent,
        ]:
            await session.refresh(run)

        fetched_runs = [
            submitted,
            running,
            pending_retry,
            pending_scheduled_ready,
            pending_zero_scaled,
        ]
        assert all(run.lock_owner == RunPipeline.__name__ for run in fetched_runs)
        assert all(run.lock_expires_at is not None for run in fetched_runs)
        assert all(run.lock_token is not None for run in fetched_runs)
        assert len({run.lock_token for run in fetched_runs}) == 1

        assert future_scheduled.lock_owner is None
        assert finished.lock_owner is None
        assert recent.lock_owner is None

    async def test_fetch_respects_order_and_limit(
        self, test_db, session: AsyncSession, fetcher: RunFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        now = get_current_datetime()

        oldest = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="oldest",
            status=RunStatus.SUBMITTED,
            submitted_at=now - dt.timedelta(minutes=3),
        )
        middle = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="middle",
            status=RunStatus.RUNNING,
            submitted_at=now - dt.timedelta(minutes=2),
        )
        newest = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="newest",
            status=RunStatus.SUBMITTED,
            submitted_at=now - dt.timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == RunPipeline.__name__
        assert middle.lock_owner == RunPipeline.__name__
        assert newest.lock_owner is None

    async def test_fetch_retries_expired_same_owner_lock_and_skips_foreign_live_lock(
        self, test_db, session: AsyncSession, fetcher: RunFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        now = get_current_datetime()
        stale = now - dt.timedelta(minutes=1)

        expired_same_owner = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="expired-same-owner",
            status=RunStatus.RUNNING,
            submitted_at=stale,
        )
        expired_same_owner.lock_expires_at = stale
        expired_same_owner.lock_token = uuid.uuid4()
        expired_same_owner.lock_owner = RunPipeline.__name__

        foreign_locked = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="foreign-locked",
            status=RunStatus.SUBMITTED,
            submitted_at=stale + dt.timedelta(seconds=1),
        )
        foreign_locked.lock_expires_at = now + dt.timedelta(minutes=1)
        foreign_locked.lock_token = uuid.uuid4()
        foreign_locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [expired_same_owner.id]
        assert items[0].prev_lock_expired is True

        await session.refresh(expired_same_owner)
        await session.refresh(foreign_locked)

        assert expired_same_owner.lock_owner == RunPipeline.__name__
        assert expired_same_owner.lock_expires_at is not None
        assert expired_same_owner.lock_token is not None
        assert foreign_locked.lock_owner == "OtherPipeline"
