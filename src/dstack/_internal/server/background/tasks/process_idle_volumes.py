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
            volumes = list(res.unique().scalars().all())
            if not volumes:
                return
            for volume in volumes:
                await session.refresh(volume, ["project", "attachments"])
                lockset.add(volume.id)

        try:
            to_delete = []
            for volume in volumes:
                if _should_delete_volume(volume):
                    to_delete.append(volume)

            if to_delete:
                await _delete_volumes(session, to_delete)

        finally:
            for volume in volumes:
                lockset.discard(volume.id)


def _should_delete_volume(volume: VolumeModel) -> bool:
    config = get_volume_configuration(volume)

    if not config.idle_duration:
        return False

    if isinstance(config.idle_duration, int) and config.idle_duration < 0:
        return False

    duration_seconds = parse_duration(config.idle_duration)
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


async def _delete_volumes(session: AsyncSession, volumes: List[VolumeModel]):
    by_project = {}
    for volume in volumes:
        project = volume.project
        if project not in by_project:
            by_project[project] = []
        by_project[project].append(volume.name)

    for project, names in by_project.items():
        try:
            await delete_volumes(session, project, names)
        except Exception as e:
            logger.error("Failed to delete volumes for project %s: %s", project.name, str(e))
