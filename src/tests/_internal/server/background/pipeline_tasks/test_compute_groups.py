import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.compute_groups import ComputeGroupStatus
from dstack._internal.server.background.pipeline_tasks.base import PipelineItem
from dstack._internal.server.background.pipeline_tasks.compute_groups import (
    ComputeGroupFetcher,
    ComputeGroupPipeline,
    ComputeGroupWorker,
)
from dstack._internal.server.models import ComputeGroupModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_compute_group,
    create_fleet,
    create_project,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> ComputeGroupWorker:
    return ComputeGroupWorker(queue=Mock(), heartbeater=Mock())


@pytest.fixture
def fetcher() -> ComputeGroupFetcher:
    return ComputeGroupFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=15),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _compute_group_to_pipeline_item(compute_group: ComputeGroupModel) -> PipelineItem:
    assert compute_group.lock_token is not None
    assert compute_group.lock_expires_at is not None
    return PipelineItem(
        __tablename__=compute_group.__tablename__,
        id=compute_group.id,
        lock_token=compute_group.lock_token,
        lock_expires_at=compute_group.lock_expires_at,
        prev_lock_expired=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestComputeGroupFetcher:
    async def test_fetch_selects_eligible_compute_groups_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: ComputeGroupFetcher
    ):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        eligible = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=stale - timedelta(seconds=2),
        )
        finished = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            status=ComputeGroupStatus.TERMINATED,
            last_processed_at=stale - timedelta(seconds=1),
        )
        recent = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=now,
        )
        locked = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=stale,
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [eligible.id]

        for compute_group in [eligible, finished, recent, locked]:
            await session.refresh(compute_group)

        assert eligible.lock_owner == ComputeGroupPipeline.__name__
        assert eligible.lock_expires_at is not None
        assert eligible.lock_token is not None

        assert finished.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_returns_oldest_compute_groups_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: ComputeGroupFetcher
    ):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        now = get_current_datetime()

        oldest = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == ComputeGroupPipeline.__name__
        assert middle.lock_owner == ComputeGroupPipeline.__name__
        assert newest.lock_owner is None


class TestComputeGroupWorker:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminates_compute_group(
        self, test_db, session: AsyncSession, worker: ComputeGroupWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        compute_group = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
        )
        compute_group.lock_token = uuid.uuid4()
        compute_group.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.RUNPOD
            await worker.process(_compute_group_to_pipeline_item(compute_group))
            compute_mock.terminate_compute_group.assert_called_once()
        await session.refresh(compute_group)
        assert compute_group.status == ComputeGroupStatus.TERMINATED
        assert compute_group.deleted

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_retries_compute_group_termination(
        self, test_db, session: AsyncSession, worker: ComputeGroupWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        compute_group = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=datetime(2023, 1, 2, 3, 0, tzinfo=timezone.utc),
        )
        compute_group.lock_token = uuid.uuid4()
        compute_group.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.RUNPOD
            compute_mock.terminate_compute_group.side_effect = BackendError()
            await worker.process(_compute_group_to_pipeline_item(compute_group))
            compute_mock.terminate_compute_group.assert_called_once()
        await session.refresh(compute_group)
        assert compute_group.status != ComputeGroupStatus.TERMINATED
        assert compute_group.first_termination_retry_at is not None
        assert compute_group.last_termination_retry_at is not None
        # Simulate termination deadline exceeded
        compute_group.first_termination_retry_at = datetime(2023, 1, 2, 3, 0, tzinfo=timezone.utc)
        compute_group.last_termination_retry_at = datetime(2023, 1, 2, 4, 0, tzinfo=timezone.utc)
        compute_group.last_processed_at = datetime(2023, 1, 2, 4, 0, tzinfo=timezone.utc)
        compute_group.lock_token = uuid.uuid4()
        compute_group.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.RUNPOD
            compute_mock.terminate_compute_group.side_effect = BackendError()
            await worker.process(_compute_group_to_pipeline_item(compute_group))
            compute_mock.terminate_compute_group.assert_called_once()
        await session.refresh(compute_group)
        assert compute_group.status == ComputeGroupStatus.TERMINATED
