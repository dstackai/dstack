import asyncio
import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.server.background.pipeline_tasks.instances import (
    InstanceFetcher,
    InstancePipeline,
)
from dstack._internal.server.testing.common import (
    create_compute_group,
    create_fleet,
    create_instance,
    create_project,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def fetcher() -> InstanceFetcher:
    return InstanceFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=10),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestInstanceFetcher:
    async def test_fetch_selects_eligible_instances_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: InstanceFetcher
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(session=session, project=project)
        compute_group = await create_compute_group(session=session, project=project, fleet=fleet)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        pending = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            last_processed_at=stale - timedelta(seconds=5),
        )
        provisioning = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
            name="provisioning",
            last_processed_at=stale - timedelta(seconds=4),
        )
        busy = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            name="busy",
            last_processed_at=stale - timedelta(seconds=3),
        )
        idle = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="idle",
            last_processed_at=stale - timedelta(seconds=2),
        )
        terminating = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
            name="terminating",
            last_processed_at=stale - timedelta(seconds=1),
        )

        deleted = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="deleted",
            last_processed_at=stale,
        )
        deleted.deleted = True

        recent = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="recent",
            last_processed_at=now,
        )

        terminating_compute_group = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
            name="terminating-compute-group",
            last_processed_at=stale + timedelta(seconds=1),
        )
        terminating_compute_group.compute_group = compute_group

        locked = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="locked",
            last_processed_at=stale + timedelta(seconds=2),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"

        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {
            pending.id,
            provisioning.id,
            busy.id,
            idle.id,
            terminating.id,
        }
        assert {item.status for item in items} == {
            InstanceStatus.PENDING,
            InstanceStatus.PROVISIONING,
            InstanceStatus.BUSY,
            InstanceStatus.IDLE,
            InstanceStatus.TERMINATING,
        }

        for instance in [
            pending,
            provisioning,
            busy,
            idle,
            terminating,
            deleted,
            recent,
            terminating_compute_group,
            locked,
        ]:
            await session.refresh(instance)

        expected_lock_owner = InstancePipeline.__name__
        fetched_instances = [pending, provisioning, busy, idle, terminating]
        assert all(instance.lock_owner == expected_lock_owner for instance in fetched_instances)
        assert all(instance.lock_expires_at is not None for instance in fetched_instances)
        assert all(instance.lock_token is not None for instance in fetched_instances)
        assert len({instance.lock_token for instance in fetched_instances}) == 1

        assert deleted.lock_owner is None
        assert recent.lock_owner is None
        assert terminating_compute_group.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_respects_order_and_limit(
        self, test_db, session: AsyncSession, fetcher: InstanceFetcher
    ):
        project = await create_project(session=session)
        now = get_current_datetime()

        oldest = await create_instance(
            session=session,
            project=project,
            name="oldest",
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_instance(
            session=session,
            project=project,
            name="middle",
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_instance(
            session=session,
            project=project,
            name="newest",
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == InstancePipeline.__name__
        assert middle.lock_owner == InstancePipeline.__name__
        assert newest.lock_owner is None
