import datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.background.scheduled_tasks.idle_volumes import (
    _get_idle_time,
    _should_delete_volume,
    process_idle_volumes,
)
from dstack._internal.server.models import VolumeAttachmentModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_instance,
    create_project,
    create_user,
    create_volume,
    get_volume_configuration,
    get_volume_provisioning_data,
    list_events,
)
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def patch_pipeline_processing_flag(monkeypatch: pytest.MonkeyPatch):
    def _apply(enabled: bool):
        monkeypatch.setattr(FeatureFlags, "PIPELINE_PROCESSING_ENABLED", enabled)

    return _apply


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestProcessIdleVolumesScheduledTask:
    @pytest.fixture(autouse=True)
    def _patch_feature_flag(self, patch_pipeline_processing_flag):
        patch_pipeline_processing_flag(False)

    async def test_deletes_idle_volumes(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        config1 = get_volume_configuration(
            name="test-volume",
            auto_cleanup_duration="1h",
        )
        config2 = get_volume_configuration(
            name="test-volume",
            auto_cleanup_duration="3h",
        )
        volume1 = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=config1,
            volume_provisioning_data=get_volume_provisioning_data(),
            last_job_processed_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2),
        )
        volume2 = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=config2,
            volume_provisioning_data=get_volume_provisioning_data(),
            last_job_processed_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2),
        )
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backend_by_type_or_error"
        ) as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            await process_idle_volumes()
            m.assert_called_once()

        await session.refresh(volume1)
        await session.refresh(volume2)
        events = await list_events(session)
        assert not volume1.to_be_deleted
        assert volume1.deleted
        assert volume1.deleted_at is not None
        assert not volume2.to_be_deleted
        assert not volume2.deleted
        assert volume2.deleted_at is None
        assert len(events) == 1
        assert events[0].message == "Volume deleted due to exceeding auto_cleanup_duration"

    async def test_deletes_idle_volume_with_null_auto_cleanup_enabled(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=get_volume_configuration(
                name="test-volume",
                auto_cleanup_duration="1h",
            ),
            volume_provisioning_data=get_volume_provisioning_data(),
            last_job_processed_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2),
        )
        volume.auto_cleanup_enabled = None
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backend_by_type_or_error"
        ) as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            await process_idle_volumes()
            m.assert_called_once()

        await session.refresh(volume)
        events = await list_events(session)
        assert not volume.to_be_deleted
        assert volume.deleted
        assert volume.deleted_at is not None
        assert len(events) == 1
        assert events[0].message == "Volume deleted due to exceeding auto_cleanup_duration"


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestProcessIdleVolumesPipelineTask:
    @pytest.fixture(autouse=True)
    def _patch_feature_flag(self, patch_pipeline_processing_flag):
        patch_pipeline_processing_flag(True)

    async def test_deletes_idle_volumes(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        config1 = get_volume_configuration(
            name="test-volume",
            auto_cleanup_duration="1h",
        )
        config2 = get_volume_configuration(
            name="test-volume",
            auto_cleanup_duration="3h",
        )
        volume1 = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=config1,
            volume_provisioning_data=get_volume_provisioning_data(),
            last_job_processed_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2),
        )
        volume2 = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=config2,
            volume_provisioning_data=get_volume_provisioning_data(),
            last_job_processed_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2),
        )
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backend_by_type_or_error"
        ) as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            await process_idle_volumes()
            m.assert_not_called()

        await session.refresh(volume1)
        await session.refresh(volume2)
        events = await list_events(session)
        assert volume1.to_be_deleted
        assert not volume1.deleted
        assert volume1.deleted_at is None
        assert not volume2.to_be_deleted
        assert not volume2.deleted
        assert volume2.deleted_at is None
        assert len(events) == 1
        assert (
            events[0].message
            == "Volume marked for deletion due to exceeding auto_cleanup_duration"
        )

    async def test_deletes_idle_volume_with_null_auto_cleanup_enabled(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=get_volume_configuration(
                name="test-volume",
                auto_cleanup_duration="1h",
            ),
            volume_provisioning_data=get_volume_provisioning_data(),
            last_job_processed_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2),
        )
        volume.auto_cleanup_enabled = None
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backend_by_type_or_error"
        ) as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            await process_idle_volumes()
            m.assert_not_called()

        await session.refresh(volume)
        events = await list_events(session)
        assert volume.to_be_deleted
        assert not volume.deleted
        assert volume.deleted_at is None
        assert len(events) == 1
        assert (
            events[0].message
            == "Volume marked for deletion due to exceeding auto_cleanup_duration"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestShouldDeleteVolume:
    async def test_no_idle_duration(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=get_volume_configuration(name="test-volume"),
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        assert not _should_delete_volume(volume)

    async def test_idle_duration_disabled(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        config = get_volume_configuration(name="test-volume")
        config.auto_cleanup_duration = -1

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        assert not _should_delete_volume(volume)

    async def test_volume_attached(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        config = get_volume_configuration(name="test-volume")
        config.auto_cleanup_duration = "1h"

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        instance = await create_instance(session=session, project=project)
        volume.attachments.append(
            VolumeAttachmentModel(volume_id=volume.id, instance_id=instance.id)
        )
        await session.commit()

        assert not _should_delete_volume(volume)

    async def test_idle_duration_threshold(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        config = get_volume_configuration(name="test-volume")
        config.auto_cleanup_duration = "1h"

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        # Not exceeded - 30 minutes ago
        volume.last_job_processed_at = get_current_datetime() - datetime.timedelta(minutes=30)
        assert not _should_delete_volume(volume)

        # Exceeded - 2 hours ago
        volume.last_job_processed_at = get_current_datetime() - datetime.timedelta(hours=2)
        assert _should_delete_volume(volume)

    async def test_never_used_volume(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=get_volume_configuration(name="test-volume"),
            volume_provisioning_data=get_volume_provisioning_data(),
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2),
        )

        volume.last_job_processed_at = None
        idle_time = _get_idle_time(volume)
        assert idle_time.total_seconds() >= 7000
