import datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.background.tasks.process_idle_volumes import (
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
)
from dstack._internal.utils.common import get_current_datetime


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestProcessIdleVolumes:
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

        await session.refresh(volume1)
        await session.refresh(volume2)
        assert volume1.deleted
        assert volume1.deleted_at is not None
        assert not volume2.deleted
        assert volume2.deleted_at is None


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
