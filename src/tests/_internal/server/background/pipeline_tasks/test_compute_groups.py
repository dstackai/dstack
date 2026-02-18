import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.compute_groups import ComputeGroupStatus
from dstack._internal.server.background.pipeline_tasks.base import PipelineItem
from dstack._internal.server.background.pipeline_tasks.compute_groups import ComputeGroupWorker
from dstack._internal.server.models import ComputeGroupModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_compute_group,
    create_fleet,
    create_project,
)


@pytest.fixture
def worker() -> ComputeGroupWorker:
    return ComputeGroupWorker(queue=Mock(), heartbeater=Mock())


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
