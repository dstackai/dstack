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


async def process_idle_volumes():
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
                .limit(10)
                .with_for_update(skip_locked=True)
            )
            volume_models = list(res.unique().scalars().all())
            if not volume_models:
                return
            for volume_model in volume_models:
                await session.refresh(volume_model, ["project", "attachments"])
                lockset.add(volume_model.id)

        try:
            volumes_to_delete = []
            for volume_model in volume_models:
                if _should_delete_idle_volume(volume_model):
                    volumes_to_delete.append(volume_model)

            if volumes_to_delete:
                await _delete_idle_volumes(session, volumes_to_delete)

        finally:
            for volume_model in volume_models:
                lockset.discard(volume_model.id)


def _should_delete_idle_volume(volume_model: VolumeModel) -> bool:
    configuration = get_volume_configuration(volume_model)

    if configuration.idle_duration is None:
        return False

    if isinstance(configuration.idle_duration, int) and configuration.idle_duration < 0:
        return False

    idle_duration_seconds = parse_duration(configuration.idle_duration)
    if idle_duration_seconds is None or idle_duration_seconds <= 0:
        return False

    if len(volume_model.attachments) > 0:
        logger.debug("Volume %s is still attached to instances, not deleting", volume_model.name)
        return False

    idle_duration = _get_volume_idle_duration(volume_model)
    idle_threshold = datetime.timedelta(seconds=idle_duration_seconds)

    if idle_duration > idle_threshold:
        logger.info(
            "Volume %s idle duration expired: idle time %.1f hours, threshold %.1f hours. Marking for deletion",
            volume_model.name,
            idle_duration.total_seconds() / 3600,
            idle_threshold.total_seconds() / 3600,
        )
        return True

    return False


def _get_volume_idle_duration(volume_model: VolumeModel) -> datetime.timedelta:
    reference_time = volume_model.created_at
    if volume_model.last_job_processed_at is not None:
        reference_time = volume_model.last_job_processed_at

    reference_time_utc = reference_time.replace(tzinfo=datetime.timezone.utc)
    current_time = get_current_datetime()

    idle_duration = current_time - reference_time_utc

    if idle_duration.total_seconds() < 0:
        return datetime.timedelta(0)

    return idle_duration


async def _delete_idle_volumes(session: AsyncSession, volume_models: List[VolumeModel]):
    volumes_by_project = {}
    for volume_model in volume_models:
        project = volume_model.project
        if project not in volumes_by_project:
            volumes_by_project[project] = []
        volumes_by_project[project].append(volume_model.name)

    for project, volume_names in volumes_by_project.items():
        logger.info("Deleting idle volumes for project %s: %s", project.name, volume_names)
        try:
            await delete_volumes(session, project, volume_names)
        except Exception as e:
            logger.error("Failed to delete idle volumes for project %s: %s", project.name, str(e))
