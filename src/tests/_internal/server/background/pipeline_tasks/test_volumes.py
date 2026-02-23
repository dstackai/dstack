import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError, BackendNotAvailable
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import VolumeProvisioningData, VolumeStatus
from dstack._internal.server.background.pipeline_tasks.volumes import (
    VolumePipelineItem,
    VolumeWorker,
)
from dstack._internal.server.models import VolumeModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_project,
    create_user,
    create_volume,
    get_volume_configuration,
    list_events,
)


@pytest.fixture
def worker() -> VolumeWorker:
    return VolumeWorker(queue=Mock(), heartbeater=Mock())


def _volume_to_pipeline_item(volume_model: VolumeModel) -> VolumePipelineItem:
    assert volume_model.lock_token is not None
    assert volume_model.lock_expires_at is not None
    return VolumePipelineItem(
        __tablename__=volume_model.__tablename__,
        id=volume_model.id,
        lock_token=volume_model.lock_token,
        lock_expires_at=volume_model.lock_expires_at,
        prev_lock_expired=False,
        status=volume_model.status,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestVolumeWorker:
    async def test_submitted_to_active(self, test_db, session: AsyncSession, worker: VolumeWorker):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.create_volume.return_value = VolumeProvisioningData(
                backend=BackendType.AWS,
                volume_id="vol-1234",
                size_gb=100,
            )
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.create_volume.assert_called_once()
            backend_mock.compute.return_value.register_volume.assert_not_called()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.ACTIVE
        assert volume.volume_provisioning_data is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume status changed SUBMITTED -> ACTIVE"

    async def test_registers_external_volume(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            configuration=get_volume_configuration(volume_id="vol-external-123"),
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.register_volume.return_value = (
                VolumeProvisioningData(
                    backend=BackendType.AWS,
                    volume_id="vol-external-123",
                    size_gb=100,
                )
            )
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.register_volume.assert_called_once()
            backend_mock.compute.return_value.create_volume.assert_not_called()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.ACTIVE
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume status changed SUBMITTED -> ACTIVE"

    async def test_marks_volume_failed_if_backend_not_available(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            get_backend_mock.side_effect = BackendNotAvailable()
            await worker.process(_volume_to_pipeline_item(volume))
            get_backend_mock.assert_called_once()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.FAILED
        assert volume.status_message == "Backend not available"
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message
            == "Volume status changed SUBMITTED -> FAILED (Backend not available)"
        )

    async def test_marks_volume_failed_if_backend_returns_error(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.create_volume.side_effect = BackendError(
                "Some error"
            )
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.create_volume.assert_called_once()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.FAILED
        assert volume.status_message == "Some error"
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume status changed SUBMITTED -> FAILED (Some error)"
