import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.profiles import parse_duration
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import VolumeModel
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.volumes import delete_volumes, get_volume_configuration
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_idle_volumes(batch_size: int = 10):
    """
    Process volumes to check if they have exceeded their idle_duration and delete them.
    """
    lock, lockset = get_locker().get_lockset(VolumeModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(VolumeModel)
                .where(
                    VolumeModel.status == VolumeStatus.ACTIVE,
                    VolumeModel.deleted == False,
                    VolumeModel.id.not_in(lockset),
                )
                .order_by(VolumeModel.last_processed_at.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            volume_models = list(res.unique().scalars().all())
            # Manually load relationships to avoid outer join in the locked query
            for volume_model in volume_models:
                await session.refresh(volume_model, ["project", "attachments"])
            if not volume_models:
                return

            # Add to lockset
            for volume_model in volume_models:
                lockset.add(volume_model.id)

        try:
            volumes_to_delete = []
            for volume_model in volume_models:
                if await _should_delete_idle_volume(volume_model):
                    volumes_to_delete.append(volume_model)

            if volumes_to_delete:
                await _delete_idle_volumes(session, volumes_to_delete)

        finally:
            # Remove from lockset
            for volume_model in volume_models:
                lockset.difference_update([volume_model.id])


async def _should_delete_idle_volume(volume_model: VolumeModel) -> bool:
    """
    Check if a volume should be deleted based on its idle duration.
    """
    # Get volume configuration
    configuration = get_volume_configuration(volume_model)

    # If no idle_duration is configured, don't delete
    if configuration.idle_duration is None:
        return False

    # If idle_duration is disabled (negative value), don't delete
    if isinstance(configuration.idle_duration, int) and configuration.idle_duration < 0:
        return False

    # Parse idle duration
    idle_duration_seconds = parse_duration(configuration.idle_duration)
    if idle_duration_seconds is None or idle_duration_seconds <= 0:
        return False

    # Check if volume is currently attached to any instance
    if len(volume_model.attachments) > 0:
        logger.debug("Volume %s is still attached to instances, not deleting", volume_model.name)
        return False

    # Calculate how long the volume has been idle
    idle_duration = _get_volume_idle_duration(volume_model)
    idle_threshold = datetime.timedelta(seconds=idle_duration_seconds)

    if idle_duration > idle_threshold:
        logger.info(
            "Volume %s idle duration expired: idle time %s seconds, threshold %s seconds. Marking for deletion",
            volume_model.name,
            idle_duration.total_seconds(),
            idle_threshold.total_seconds(),
        )
        return True

    return False


def _get_volume_idle_duration(volume_model: VolumeModel) -> datetime.timedelta:
    """
    Calculate how long a volume has been idle.
    A volume is considered idle from the time it was last processed by a job.
    If it was never used by a job, use the created_at time.
    """
    last_time = volume_model.created_at.replace(tzinfo=datetime.timezone.utc)
    if volume_model.last_job_processed_at is not None:
        last_time = volume_model.last_job_processed_at.replace(tzinfo=datetime.timezone.utc)
    return get_current_datetime() - last_time


async def _delete_idle_volumes(session: AsyncSession, volume_models: List[VolumeModel]):
    """
    Delete volumes that have exceeded their idle duration.
    """
    # Group volumes by project
    volumes_by_project = {}
    for volume_model in volume_models:
        project = volume_model.project
        if project not in volumes_by_project:
            volumes_by_project[project] = []
        volumes_by_project[project].append(volume_model.name)

    # Delete volumes by project
    for project, volume_names in volumes_by_project.items():
        logger.info("Deleting idle volumes for project %s: %s", project.name, volume_names)
        try:
            await delete_volumes(session, project, volume_names)
        except Exception as e:
            logger.error("Failed to delete idle volumes for project %s: %s", project.name, str(e))
