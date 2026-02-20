import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.background.pipeline_tasks.base import PipelineItem
from dstack._internal.server.background.pipeline_tasks.placement_groups import PlacementGroupWorker
from dstack._internal.server.models import PlacementGroupModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_placement_group,
    create_project,
)


@pytest.fixture
def worker() -> PlacementGroupWorker:
    return PlacementGroupWorker(queue=Mock(), heartbeater=Mock())


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


class TestPlacementGroupWorker:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
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
