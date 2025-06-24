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


class TestProcessIdleVolumes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_no_idle_duration_configured(self, test_db, session: AsyncSession):
        """Test that volumes without idle_duration configured are not deleted."""
        project = await create_project(session=session)
        user = await create_user(session=session)

        # Create volume without idle_duration
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=get_volume_configuration(name="test-volume"),
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        should_delete = await _should_delete_idle_volume(volume)
        assert not should_delete

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_idle_duration_disabled(self, test_db, session: AsyncSession):
        """Test that volumes with idle_duration set to -1 (disabled) are not deleted."""
        project = await create_project(session=session)
        user = await create_user(session=session)

        # Create volume with idle_duration disabled
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

        should_delete = await _should_delete_idle_volume(volume)
        assert not should_delete

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_volume_still_attached(self, test_db, session: AsyncSession):
        """Test that volumes still attached to instances are not deleted."""
        project = await create_project(session=session)
        user = await create_user(session=session)

        # Create volume with idle_duration
        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"  # 1 hour

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        # Create an instance and attach the volume to it
        instance = await create_instance(session=session, project=project)
        attachment = VolumeAttachmentModel(
            volume_id=volume.id,
            instance_id=instance.id,
        )
        volume.attachments.append(attachment)
        await session.commit()

        should_delete = await _should_delete_idle_volume(volume)
        assert not should_delete

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_idle_duration_not_exceeded(self, test_db, session: AsyncSession):
        """Test that volumes within idle duration threshold are not deleted."""
        project = await create_project(session=session)
        user = await create_user(session=session)

        # Create volume with idle_duration
        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"  # 1 hour

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        # Set last_job_processed_at to 30 minutes ago (less than 1 hour)
        volume.last_job_processed_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        ).replace(tzinfo=None)

        should_delete = await _should_delete_idle_volume(volume)
        assert not should_delete

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_idle_duration_exceeded(self, test_db, session: AsyncSession):
        """Test that volumes exceeding idle duration threshold are marked for deletion."""
        project = await create_project(session=session)
        user = await create_user(session=session)

        # Create volume with idle_duration
        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"  # 1 hour

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        # Set last_job_processed_at to 2 hours ago (more than 1 hour)
        volume.last_job_processed_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        ).replace(tzinfo=None)

        should_delete = await _should_delete_idle_volume(volume)
        assert should_delete

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_volume_never_used_by_job(self, test_db, session: AsyncSession):
        """Test idle duration calculation for volumes never used by jobs."""
        project = await create_project(session=session)
        user = await create_user(session=session)

        # Create volume with old created_at time
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

        # last_job_processed_at is None, so it should use created_at
        volume.last_job_processed_at = None

        idle_duration = _get_volume_idle_duration(volume)
        # Should be approximately 2 hours
        assert idle_duration.total_seconds() >= 7000  # ~2 hours in seconds

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_process_idle_volumes_integration(self, test_db, session: AsyncSession):
        """Integration test for the full process_idle_volumes function."""
        project = await create_project(session=session)
        user = await create_user(session=session)

        # Create volume that should be deleted (exceeded idle duration)
        volume_config = get_volume_configuration(name="test-volume")
        volume_config.idle_duration = "1h"  # 1 hour

        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_config,
            volume_provisioning_data=get_volume_provisioning_data(),
        )

        # Set as idle for more than threshold
        volume.last_job_processed_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        ).replace(tzinfo=None)

        await session.commit()

        # Mock the delete_volumes function to avoid actual deletion
        with patch(
            "dstack._internal.server.background.tasks.process_idle_volumes.delete_volumes"
        ) as mock_delete:
            await process_idle_volumes()

            # Should have called delete_volumes with the volume
            mock_delete.assert_called_once()
            call_args = mock_delete.call_args
            # The function is called with (session, project, volume_names_list)
            assert call_args[0][2] == ["test-volume"]
