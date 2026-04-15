import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import parse_run_configuration
from dstack._internal.core.models.runs import RunStatus
from dstack._internal.server.background.pipeline_tasks.service_router_worker_sync import (
    ServiceRouterWorkerSyncFetcher,
    ServiceRouterWorkerSyncPipeline,
    ServiceRouterWorkerSyncPipelineItem,
    ServiceRouterWorkerSyncWorker,
)
from dstack._internal.server.models import RunModel, ServiceRouterWorkerSyncModel
from dstack._internal.server.testing.common import (
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
)
from dstack._internal.utils.common import get_current_datetime


def _router_service_run_spec(repo_id: str, run_name: str = "test-run"):
    conf = parse_run_configuration(
        {
            "type": "service",
            "port": 8000,
            "gateway": False,
            "replicas": [
                {
                    "name": "router",
                    "count": 1,
                    "commands": ["sglang serve"],
                    "router": {"type": "sglang"},
                },
                {"name": "worker", "count": 2, "commands": ["worker"]},
            ],
        }
    )
    return get_run_spec(repo_id=repo_id, run_name=run_name, configuration=conf)


async def _add_service_router_worker_sync_row(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    deleted: bool = False,
    created_at=None,
    last_processed_at=None,
) -> ServiceRouterWorkerSyncModel:
    now = get_current_datetime()
    if created_at is None:
        created_at = now
    if last_processed_at is None:
        last_processed_at = now
    row = ServiceRouterWorkerSyncModel(
        id=uuid.uuid4(),
        run_id=run_id,
        deleted=deleted,
        created_at=created_at,
        last_processed_at=last_processed_at,
    )
    session.add(row)
    await session.commit()
    return row


def _sync_row_to_pipeline_item(
    sync_row: ServiceRouterWorkerSyncModel,
) -> ServiceRouterWorkerSyncPipelineItem:
    assert sync_row.lock_token is not None
    assert sync_row.lock_expires_at is not None
    return ServiceRouterWorkerSyncPipelineItem(
        __tablename__=ServiceRouterWorkerSyncModel.__tablename__,
        id=sync_row.id,
        lock_token=sync_row.lock_token,
        lock_expires_at=sync_row.lock_expires_at,
        prev_lock_expired=False,
        run_id=sync_row.run_id,
    )


@pytest.fixture
def fetcher() -> ServiceRouterWorkerSyncFetcher:
    return ServiceRouterWorkerSyncFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=5),
        lock_timeout=timedelta(seconds=25),
        heartbeater=Mock(),
    )


@pytest.fixture
def worker() -> ServiceRouterWorkerSyncWorker:
    return ServiceRouterWorkerSyncWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestServiceRouterWorkerSyncFetcher:
    async def test_fetch_selects_eligible_sync_rows_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: ServiceRouterWorkerSyncFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        # Case 1: eligible row
        # This row should be fetched.
        running = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="running",
            status=RunStatus.RUNNING,
            submitted_at=stale,
            last_processed_at=stale,
            run_spec=_router_service_run_spec(repo.name, "running"),
        )
        eligible = await _add_service_router_worker_sync_row(
            session,
            running.id,
            created_at=stale,
            last_processed_at=stale,
        )
        # Case 2: run is submitted.
        # This row should not be fetched because the fetcher only wants RUNNING runs.
        submitted = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="submitted",
            status=RunStatus.SUBMITTED,
            submitted_at=stale,
            last_processed_at=stale,
            run_spec=_router_service_run_spec(repo.name, "submitted"),
        )
        sync_submitted = await _add_service_router_worker_sync_row(
            session,
            submitted.id,
            created_at=stale,
            last_processed_at=stale,
        )
        # Case 3: sync row processed too recently.
        # This row should not be fetched because it is too recent.
        too_recent = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="too-recent",
            status=RunStatus.RUNNING,
            submitted_at=stale,
            last_processed_at=now,
            run_spec=_router_service_run_spec(repo.name, "too-recent"),
        )
        created_earlier = now - timedelta(days=1)
        sync_too_recent = await _add_service_router_worker_sync_row(
            session,
            too_recent.id,
            created_at=created_earlier,
            last_processed_at=now,
        )
        # Case 4: sync row already marked deleted.
        # This row should not be fetched.
        deleted_sync_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="deleted-sync",
            status=RunStatus.RUNNING,
            submitted_at=stale,
            last_processed_at=stale,
            run_spec=_router_service_run_spec(repo.name, "deleted-sync"),
        )
        sync_deleted = await _add_service_router_worker_sync_row(
            session,
            deleted_sync_run.id,
            created_at=stale,
            last_processed_at=stale,
            deleted=True,
        )
        # Case 5: sync row locked by another pipeline.
        # This row should not be fetched.
        locked = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="locked",
            status=RunStatus.RUNNING,
            submitted_at=stale,
            last_processed_at=stale,
            run_spec=_router_service_run_spec(repo.name, "locked"),
        )
        sync_locked = await _add_service_router_worker_sync_row(
            session,
            locked.id,
            created_at=stale,
            last_processed_at=stale,
        )
        sync_locked.lock_expires_at = now + timedelta(minutes=1)
        sync_locked.lock_token = uuid.uuid4()
        sync_locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)
        # Only case 1 should be fetched.
        assert {item.id for item in items} == {eligible.id}

        for row in [
            eligible,
            sync_submitted,
            sync_too_recent,
            sync_deleted,
            sync_locked,
        ]:
            await session.refresh(row)

        assert eligible.lock_owner == ServiceRouterWorkerSyncPipeline.__name__
        assert eligible.lock_expires_at is not None
        assert eligible.lock_token is not None

        assert sync_submitted.lock_owner is None
        assert sync_too_recent.lock_owner is None
        assert sync_deleted.lock_owner is None
        assert sync_locked.lock_owner == "OtherPipeline"

    # test_fetch_returns_oldest_sync_rows_first_up_to_limit answers: "When several rows are all
    # eligible, does SQL ORDER BY last_processed_at and LIMIT behave as intended?" That's ordering
    # + batch size, not eligibility.
    async def test_fetch_returns_oldest_sync_rows_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: ServiceRouterWorkerSyncFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        now = get_current_datetime()
        spec = _router_service_run_spec(repo.name)

        oldest_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="oldest",
            status=RunStatus.RUNNING,
            run_spec=spec,
            last_processed_at=now - timedelta(minutes=3),
        )
        oldest = await _add_service_router_worker_sync_row(
            session,
            oldest_run.id,
            last_processed_at=now - timedelta(minutes=3),
        )
        middle_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="middle",
            status=RunStatus.RUNNING,
            run_spec=spec,
            last_processed_at=now - timedelta(minutes=2),
        )
        middle = await _add_service_router_worker_sync_row(
            session,
            middle_run.id,
            last_processed_at=now - timedelta(minutes=2),
        )
        newest_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="newest",
            status=RunStatus.RUNNING,
            run_spec=spec,
            last_processed_at=now - timedelta(minutes=1),
        )
        newest = await _add_service_router_worker_sync_row(
            session,
            newest_run.id,
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == ServiceRouterWorkerSyncPipeline.__name__
        assert middle.lock_owner == ServiceRouterWorkerSyncPipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestServiceRouterWorkerSyncWorker:
    async def test_process_skips_when_lock_token_changes(
        self,
        test_db,
        session: AsyncSession,
        worker: ServiceRouterWorkerSyncWorker,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.RUNNING,
            run_spec=_router_service_run_spec(repo.name),
        )
        sync_row = await _add_service_router_worker_sync_row(session, run.id)
        sync_row.lock_token = uuid.uuid4()
        sync_row.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
        sync_row.lock_owner = ServiceRouterWorkerSyncPipeline.__name__
        await session.commit()

        item = _sync_row_to_pipeline_item(sync_row)
        new_token = uuid.uuid4()
        sync_row.lock_token = new_token
        await session.commit()

        await worker.process(item)
        await session.refresh(sync_row)

        assert sync_row.lock_token == new_token
        assert sync_row.lock_owner == ServiceRouterWorkerSyncPipeline.__name__

    async def test_marks_sync_row_deleted_when_run_not_running(
        self,
        test_db,
        session: AsyncSession,
        worker: ServiceRouterWorkerSyncWorker,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.DONE,
            run_spec=_router_service_run_spec(repo.name),
        )
        sync_row = await _add_service_router_worker_sync_row(session, run.id)
        sync_row.lock_token = uuid.uuid4()
        sync_row.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
        sync_row.lock_owner = ServiceRouterWorkerSyncPipeline.__name__
        await session.commit()

        await worker.process(_sync_row_to_pipeline_item(sync_row))
        await session.refresh(sync_row)

        assert sync_row.deleted is True
        assert sync_row.lock_token is None
        assert sync_row.lock_expires_at is None
        assert sync_row.lock_owner is None

    # This can happen when a run previously had a router replica group (so a sync row was created),
    # but later its configuration/run_spec is updated (e.g. re-apply) to remove the router group.
    async def test_marks_sync_row_deleted_when_no_router_replica_group(
        self,
        test_db,
        session: AsyncSession,
        worker: ServiceRouterWorkerSyncWorker,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.RUNNING,
            run_spec=get_run_spec(repo_id=repo.name, run_name="task-run"),
        )
        sync_row = await _add_service_router_worker_sync_row(session, run.id)
        sync_row.lock_token = uuid.uuid4()
        sync_row.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
        sync_row.lock_owner = ServiceRouterWorkerSyncPipeline.__name__
        await session.commit()

        await worker.process(_sync_row_to_pipeline_item(sync_row))
        await session.refresh(sync_row)

        assert sync_row.deleted is True
        assert sync_row.lock_token is None

    async def test_process_calls_sync_and_unlocks_on_success(
        self,
        test_db,
        session: AsyncSession,
        worker: ServiceRouterWorkerSyncWorker,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.RUNNING,
            run_spec=_router_service_run_spec(repo.name),
        )
        sync_row = await _add_service_router_worker_sync_row(session, run.id)
        sync_row.lock_token = uuid.uuid4()
        sync_row.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
        sync_row.lock_owner = ServiceRouterWorkerSyncPipeline.__name__
        await session.commit()
        item = _sync_row_to_pipeline_item(sync_row)

        with patch(
            "dstack._internal.server.background.pipeline_tasks.service_router_worker_sync"
            ".sync_router_workers_for_run_model",
            new_callable=AsyncMock,
        ) as sync_mock:
            await worker.process(item)

        sync_mock.assert_awaited_once()
        # `await_args` is Optional in stubs; assert for type-checkers.
        assert sync_mock.await_args is not None
        called_run = sync_mock.await_args.args[0]
        assert isinstance(called_run, RunModel)
        assert called_run.id == run.id

        await session.refresh(sync_row)
        assert sync_row.deleted is False
        assert sync_row.lock_token is None
        assert sync_row.lock_expires_at is None
        assert sync_row.lock_owner is None
        assert sync_row.last_processed_at is not None
