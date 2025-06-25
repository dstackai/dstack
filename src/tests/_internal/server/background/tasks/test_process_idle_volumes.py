import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.background.tasks.process_idle_volumes import (
    _get_volume_idle_duration,
    _should_delete_idle_volume,
    process_idle_volumes,
)
from dstack._internal.server.models import VolumeAttachmentModel
from dstack._internal.server.testing.common import (
    create_instance,
    create_project,
    create_user,
    create_volume,
    get_volume_configuration,
    get_volume_provisioning_data,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestProcessIdleVolumes:
    async def test_no_idle_duration_configured(self, test_db, session: AsyncSession):
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

        should_delete = _should_delete_idle_volume(volume)
        assert not should_delete

    async def test_idle_duration_disabled(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = -1

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        should_delete = _should_delete_idle_volume(volume)
        assert not should_delete

    async def test_volume_still_attached(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        instance = await create_instance(session=session, project=project)
        attachment = VolumeAttachmentModel(
            volume_id=volume.id,
            instance_id=instance.id,
        )
        volume.attachments.append(attachment)
        await session.commit()

        should_delete = _should_delete_idle_volume(volume)
        assert not should_delete

    async def test_idle_duration_not_exceeded(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        volume.last_job_processed_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        ).replace(tzinfo=None)

        should_delete = _should_delete_idle_volume(volume)
        assert not should_delete

    async def test_idle_duration_exceeded(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        volume.last_job_processed_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        ).replace(tzinfo=None)

        should_delete = _should_delete_idle_volume(volume)
        assert should_delete

    async def test_volume_never_used_by_job(self, test_db, session: AsyncSession):
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

        idle_duration = _get_volume_idle_duration(volume)
        assert idle_duration.total_seconds() >= 7000

    async def test_process_idle_volumes_integration(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)

        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        volume.last_job_processed_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        ).replace(tzinfo=None)

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_idle_volumes.delete_volumes"
        ) as mock_delete:
            await process_idle_volumes()

            mock_delete.assert_called_once()
            call_args = mock_delete.call_args
            assert call_args[0][2] == ["test-volume"]
