import datetime
from typing import List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.errors import BackendNotAvailable
from dstack._internal.core.models.profiles import parse_duration
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import VolumeModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.volumes import (
    get_volume_configuration,
    volume_model_to_volume,
)
from dstack._internal.utils import common
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_idle_volumes():
    lock, lockset = get_locker(get_db().dialect_name).get_lockset(VolumeModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(VolumeModel.id)
                .where(
                    VolumeModel.status == VolumeStatus.ACTIVE,
                    VolumeModel.deleted == False,
                    VolumeModel.id.not_in(lockset),
                )
                .order_by(VolumeModel.last_processed_at.asc())
                .limit(10)
                .with_for_update(skip_locked=True)
            )
            volume_ids = list(res.scalars().all())
            if not volume_ids:
                return
            for volume_id in volume_ids:
                lockset.add(volume_id)

        # Load volumes with related attributes in one query
        res = await session.execute(
            select(VolumeModel)
            .where(VolumeModel.id.in_(volume_ids))
            .options(selectinload(VolumeModel.project))
            .options(selectinload(VolumeModel.user))
            .options(selectinload(VolumeModel.attachments))
            .execution_options(populate_existing=True)
        )
        volumes = list(res.unique().scalars().all())

        try:
            to_delete = []
            for volume in volumes:
                if _should_delete_volume(volume):
                    to_delete.append(volume)

            if to_delete:
                await _delete_idle_volumes(session, to_delete)

        finally:
            lockset.difference_update(volume_ids)


def _should_delete_volume(volume: VolumeModel) -> bool:
    config = get_volume_configuration(volume)

    if not config.auto_cleanup_duration:
        return False

    if isinstance(config.auto_cleanup_duration, int) and config.auto_cleanup_duration < 0:
        return False

    duration_seconds = parse_duration(config.auto_cleanup_duration)
    if not duration_seconds or duration_seconds <= 0:
        return False

    if volume.attachments:
        return False

    idle_time = _get_idle_time(volume)
    threshold = datetime.timedelta(seconds=duration_seconds)

    if idle_time > threshold:
        logger.info(
            "Deleting idle volume %s (idle %.1fh)", volume.name, idle_time.total_seconds() / 3600
        )
        return True

    return False


def _get_idle_time(volume: VolumeModel) -> datetime.timedelta:
    last_used = volume.last_job_processed_at or volume.created_at
    last_used_utc = last_used.replace(tzinfo=datetime.timezone.utc)
    now = get_current_datetime()

    idle_time = now - last_used_utc
    return max(idle_time, datetime.timedelta(0))


async def _delete_idle_volumes(session: AsyncSession, volumes: List[VolumeModel]):
    """Delete idle volumes from cloud providers and mark as deleted in database."""
    for volume_model in volumes:
        try:
            # Try to delete from cloud provider first
            await _delete_volume_from_cloud(session, volume_model)
        except Exception:
            logger.exception("Error when deleting volume %s from cloud", volume_model.name)

        # Always mark as deleted in database, even if cloud deletion failed
        try:
            await session.execute(
                update(VolumeModel)
                .where(VolumeModel.id == volume_model.id)
                .values(
                    deleted=True,
                    deleted_at=get_current_datetime(),
                )
            )
            logger.info("Deleted idle volume %s", volume_model.name)
        except Exception:
            logger.exception("Failed to mark volume %s as deleted in database", volume_model.name)

    await session.commit()


async def _delete_volume_from_cloud(session: AsyncSession, volume_model: VolumeModel):
    """Delete volume from cloud provider. Based on volumes.py:_delete_volume"""
    volume = volume_model_to_volume(volume_model)

    if volume.external:
        # External volumes are not managed by dstack
        return

    if volume.provisioning_data is None:
        # The volume wasn't provisioned so there is nothing to delete
        return

    if volume.provisioning_data.backend is None:
        logger.error(
            f"Failed to delete volume {volume_model.name}. volume.provisioning_data.backend is None."
        )
        return

    try:
        backend = await backends_services.get_project_backend_by_type_or_error(
            project=volume_model.project,
            backend_type=volume.provisioning_data.backend,
        )
    except BackendNotAvailable:
        logger.error(
            f"Failed to delete volume {volume_model.name}. Backend {volume.configuration.backend} not available."
        )
        return

    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)
    await common.run_async(
        compute.delete_volume,
        volume=volume,
    )
