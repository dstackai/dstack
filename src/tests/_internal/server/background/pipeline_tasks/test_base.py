import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.background.pipeline_tasks.base import Heartbeater, PipelineItem
from dstack._internal.server.models import PlacementGroupModel
from dstack._internal.server.testing.common import (
    create_fleet,
    create_placement_group,
    create_project,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)


@pytest.fixture
def heartbeater() -> Heartbeater[PipelineItem]:
    return Heartbeater(
        model_type=PlacementGroupModel,
        lock_timeout=timedelta(seconds=30),
        heartbeat_trigger=timedelta(seconds=5),
    )


async def _create_locked_placement_group(
    session: AsyncSession,
    now: datetime,
    lock_expires_in: timedelta,
) -> PlacementGroupModel:
    project = await create_project(session)
    fleet = await create_fleet(session=session, project=project)
    placement_group = await create_placement_group(
        session=session,
        project=project,
        fleet=fleet,
        name="test-pg",
    )
    placement_group.lock_token = uuid.uuid4()
    placement_group.lock_expires_at = now + lock_expires_in
    await session.commit()
    return placement_group


def _placement_group_to_pipeline_item(placement_group: PlacementGroupModel) -> PipelineItem:
    assert placement_group.lock_token is not None
    assert placement_group.lock_expires_at is not None
    return PipelineItem(
        __tablename__=PlacementGroupModel.__tablename__,
        id=placement_group.id,
        lock_token=placement_group.lock_token,
        lock_expires_at=placement_group.lock_expires_at,
        prev_lock_expired=False,
    )


class TestHeartbeater:
    @pytest.mark.asyncio
    async def test_untrack_preserves_item_when_lock_token_mismatches(
        self, heartbeater: Heartbeater[PipelineItem], now: datetime
    ):
        item = PipelineItem(
            __tablename__=PlacementGroupModel.__tablename__,
            id=uuid.uuid4(),
            lock_token=uuid.uuid4(),
            lock_expires_at=now + timedelta(seconds=10),
            prev_lock_expired=True,
        )
        await heartbeater.track(item)

        stale_item = PipelineItem(
            __tablename__=PlacementGroupModel.__tablename__,
            id=item.id,
            lock_token=uuid.uuid4(),
            lock_expires_at=item.lock_expires_at,
            prev_lock_expired=False,
        )
        await heartbeater.untrack(stale_item)

        assert item.id in heartbeater._items
        await heartbeater.untrack(item)
        assert item.id not in heartbeater._items

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_heartbeat_extends_locks_close_to_expiration(
        self,
        test_db,
        session: AsyncSession,
        heartbeater: Heartbeater[PipelineItem],
        now: datetime,
    ):
        placement_group = await _create_locked_placement_group(
            session=session,
            now=now,
            lock_expires_in=timedelta(seconds=2),
        )
        await heartbeater.track(_placement_group_to_pipeline_item(placement_group))

        with patch(
            "dstack._internal.server.background.pipeline_tasks.base.get_current_datetime",
            return_value=now,
        ):
            await heartbeater.heartbeat()

        expected_lock_expires_at = now + timedelta(seconds=30)
        tracked_item = heartbeater._items[placement_group.id]
        assert tracked_item.lock_expires_at == expected_lock_expires_at

        await session.refresh(placement_group)
        assert placement_group.lock_expires_at == expected_lock_expires_at

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_heartbeat_untracks_expired_items_without_db_update(
        self,
        test_db,
        session: AsyncSession,
        heartbeater: Heartbeater[PipelineItem],
        now: datetime,
    ):
        original_lock_expires_at = now - timedelta(seconds=1)
        placement_group = await _create_locked_placement_group(
            session=session,
            now=now,
            lock_expires_in=timedelta(seconds=-1),
        )
        await heartbeater.track(_placement_group_to_pipeline_item(placement_group))

        with patch(
            "dstack._internal.server.background.pipeline_tasks.base.get_current_datetime",
            return_value=now,
        ):
            await heartbeater.heartbeat()

        assert placement_group.id not in heartbeater._items

        await session.refresh(placement_group)
        assert placement_group.lock_expires_at == original_lock_expires_at

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_heartbeat_untracks_item_when_lock_token_changed_in_db(
        self,
        test_db,
        session: AsyncSession,
        heartbeater: Heartbeater[PipelineItem],
        now: datetime,
    ):
        original_lock_expires_at = now + timedelta(seconds=2)
        placement_group = await _create_locked_placement_group(
            session=session,
            now=now,
            lock_expires_in=timedelta(seconds=2),
        )
        await heartbeater.track(_placement_group_to_pipeline_item(placement_group))

        new_lock_token = uuid.uuid4()
        await session.execute(
            update(PlacementGroupModel)
            .where(PlacementGroupModel.id == placement_group.id)
            .values(lock_token=new_lock_token)
            .execution_options(synchronize_session=False)
        )
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.base.get_current_datetime",
            return_value=now,
        ):
            await heartbeater.heartbeat()

        assert placement_group.id not in heartbeater._items

        await session.refresh(placement_group)
        assert placement_group.lock_token == new_lock_token
        assert placement_group.lock_expires_at == original_lock_expires_at
