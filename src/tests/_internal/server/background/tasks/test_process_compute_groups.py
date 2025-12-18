from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.background.tasks.process_compute_groups import (
    ComputeGroupStatus,
    process_compute_groups,
)
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_compute_group,
    create_fleet,
    create_project,
)


class TestProcessComputeGroups:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminates_compute_group(self, test_db, session: AsyncSession):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        compute_group = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
        )
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.RUNPOD
            await process_compute_groups()
            compute_mock.terminate_compute_group.assert_called_once()
        await session.refresh(compute_group)
        assert compute_group.status == ComputeGroupStatus.TERMINATED
        assert compute_group.deleted

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_retries_compute_group_termination(self, test_db, session: AsyncSession):
        project = await create_project(session)
        fleet = await create_fleet(session=session, project=project)
        compute_group = await create_compute_group(
            session=session,
            project=project,
            fleet=fleet,
            last_processed_at=datetime(2023, 1, 2, 3, 0, tzinfo=timezone.utc),
        )
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.RUNPOD
            compute_mock.terminate_compute_group.side_effect = BackendError()
            await process_compute_groups()
            compute_mock.terminate_compute_group.assert_called_once()
        await session.refresh(compute_group)
        assert compute_group.status != ComputeGroupStatus.TERMINATED
        assert compute_group.first_termination_retry_at is not None
        assert compute_group.last_termination_retry_at is not None
        # Simulate termination deadline exceeded
        compute_group.first_termination_retry_at = datetime(2023, 1, 2, 3, 0, tzinfo=timezone.utc)
        compute_group.last_termination_retry_at = datetime(2023, 1, 2, 4, 0, tzinfo=timezone.utc)
        compute_group.last_processed_at = datetime(2023, 1, 2, 4, 0, tzinfo=timezone.utc)
        await session.commit()
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.RUNPOD
            compute_mock.terminate_compute_group.side_effect = BackendError()
            await process_compute_groups()
            compute_mock.terminate_compute_group.assert_called_once()
        await session.refresh(compute_group)
        assert compute_group.status == ComputeGroupStatus.TERMINATED
