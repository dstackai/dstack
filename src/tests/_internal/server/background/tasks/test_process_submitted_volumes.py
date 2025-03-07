from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import VolumeProvisioningData, VolumeStatus
from dstack._internal.server.background.tasks.process_volumes import process_submitted_volumes
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_project,
    create_user,
    create_volume,
)


class TestProcessSubmittedVolumes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_fails_job_when_no_backends(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session, project=project, user=user, status=VolumeStatus.SUBMITTED
        )
        await process_submitted_volumes()
        await session.refresh(volume)
        assert volume.status == VolumeStatus.FAILED
        assert volume.status_message == "Backend not available"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisiones_volumes(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session, project=project, user=user, status=VolumeStatus.SUBMITTED
        )
        with patch(
            "dstack._internal.server.services.backends.get_project_backend_by_type_or_error"
        ) as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            aws_mock.compute.return_value.create_volume.return_value = VolumeProvisioningData(
                backend=BackendType.AWS,
                volume_id="1234",
                size_gb=100,
            )
            await process_submitted_volumes()
            aws_mock.compute.return_value.create_volume.assert_called_once()
        await session.refresh(volume)
        assert volume.status == VolumeStatus.ACTIVE
