import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import PlacementGroupInUseError
from dstack._internal.server.background.pipeline_tasks.base import PipelineItem
from dstack._internal.server.background.pipeline_tasks.placement_groups import (
    PlacementGroupFetcher,
    PlacementGroupPipeline,
    PlacementGroupWorker,
)
from dstack._internal.server.models import PlacementGroupModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_placement_group,
    create_project,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> PlacementGroupWorker:
    return PlacementGroupWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())


@pytest.fixture
def fetcher() -> PlacementGroupFetcher:
    return PlacementGroupFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=15),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _placement_group_to_pipeline_item(placement_group: PlacementGroupModel) -> PipelineItem:
    assert placement_group.lock_token is not None
    assert placement_group.lock_expires_at is not None
    return PipelineItem(
        __tablename__=placement_group.__tablename__,
        id=placement_group.id,
        lock_token=placement_group.lock_token,
        lock_expires_at=placement_group.lock_expires_at,
        prev_lock_expired=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestPlacementGroupFetcher:
    async def test_fetch_selects_eligible_placement_groups_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: PlacementGroupFetcher
    ):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        eligible = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            fleet_deleted=True,
        )
        eligible.last_processed_at = stale - timedelta(seconds=2)

        fleet_not_deleted = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="fleet-not-deleted",
            fleet_deleted=False,
        )
        fleet_not_deleted.last_processed_at = stale - timedelta(seconds=1)

        deleted = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="deleted",
            fleet_deleted=True,
            deleted=True,
        )
        deleted.last_processed_at = stale

        recent = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="recent",
            fleet_deleted=True,
        )
        recent.last_processed_at = now

        locked = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="locked",
            fleet_deleted=True,
        )
        locked.last_processed_at = stale + timedelta(seconds=1)
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [eligible.id]

        for placement_group in [eligible, fleet_not_deleted, deleted, recent, locked]:
            await session.refresh(placement_group)

        assert eligible.lock_owner == PlacementGroupPipeline.__name__
        assert eligible.lock_expires_at is not None
        assert eligible.lock_token is not None

        assert fleet_not_deleted.lock_owner is None
        assert deleted.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_returns_oldest_placement_groups_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: PlacementGroupFetcher
    ):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        now = get_current_datetime()

        oldest = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="oldest",
            fleet_deleted=True,
        )
        oldest.last_processed_at = now - timedelta(minutes=3)

        middle = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="middle",
            fleet_deleted=True,
        )
        middle.last_processed_at = now - timedelta(minutes=2)

        newest = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="newest",
            fleet_deleted=True,
        )
        newest.last_processed_at = now - timedelta(minutes=1)
        await session.commit()

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == PlacementGroupPipeline.__name__
        assert middle.lock_owner == PlacementGroupPipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestPlacementGroupWorker:
    async def test_deletes_placement_group(
        self, test_db, session: AsyncSession, worker: PlacementGroupWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
        )
        placement_group = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="test1-pg",
            fleet_deleted=True,
        )
        placement_group.lock_token = uuid.uuid4()
        placement_group.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            await worker.process(_placement_group_to_pipeline_item(placement_group))
            aws_mock.compute.return_value.delete_placement_group.assert_called_once()
        await session.refresh(placement_group)
        assert placement_group.deleted

    async def test_retries_placement_group_deletion_if_still_in_use(
        self, test_db, session: AsyncSession, worker: PlacementGroupWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
        )
        placement_group = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="test2-pg",
            fleet_deleted=True,
        )
        placement_group.lock_token = uuid.uuid4()
        placement_group.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        placement_group.lock_owner = "PlacementGroupPipeline"
        original_last_processed_at = placement_group.last_processed_at
        await session.commit()
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            aws_mock.compute.return_value.delete_placement_group.side_effect = (
                PlacementGroupInUseError()
            )
            await worker.process(_placement_group_to_pipeline_item(placement_group))
            aws_mock.compute.return_value.delete_placement_group.assert_called_once()
        await session.refresh(placement_group)
        assert not placement_group.deleted
        assert placement_group.last_processed_at > original_last_processed_at
        assert placement_group.lock_token is None
        assert placement_group.lock_expires_at is None
        assert placement_group.lock_owner is None
