import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.errors import BackendNotAvailable
from dstack._internal.core.models.profiles import parse_duration
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import ProjectModel, UserModel, VolumeModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.volumes import (
    get_volume_configuration,
    volume_model_to_volume,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils import common
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@sentry_utils.instrument_background_task
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
                .with_for_update(skip_locked=True, key_share=True)
            )
            volume_ids = list(res.scalars().all())
            if not volume_ids:
                return
            for volume_id in volume_ids:
                lockset.add(volume_id)

        res = await session.execute(
            select(VolumeModel)
            .where(VolumeModel.id.in_(volume_ids))
            .options(joinedload(VolumeModel.project).joinedload(ProjectModel.backends))
            .options(joinedload(VolumeModel.user).load_only(UserModel.name))
            .options(joinedload(VolumeModel.attachments))
            .execution_options(populate_existing=True)
        )
        volume_models = list(res.unique().scalars().all())
        try:
            volumes_to_delete = [v for v in volume_models if _should_delete_volume(v)]
            if not volumes_to_delete:
                return
            await _delete_idle_volumes(session, volumes_to_delete)
        finally:
            lockset.difference_update(volume_ids)


def _should_delete_volume(volume: VolumeModel) -> bool:
    if volume.attachments:
        return False

    config = get_volume_configuration(volume)
    if not config.auto_cleanup_duration:
        return False

    duration_seconds = parse_duration(config.auto_cleanup_duration)
    if not duration_seconds or duration_seconds <= 0:
        return False

    idle_time = _get_idle_time(volume)
    threshold = datetime.timedelta(seconds=duration_seconds)
    return idle_time > threshold


def _get_idle_time(volume: VolumeModel) -> datetime.timedelta:
    last_used = volume.last_job_processed_at or volume.created_at
    idle_time = get_current_datetime() - last_used
    return max(idle_time, datetime.timedelta(0))


async def _delete_idle_volumes(session: AsyncSession, volumes: List[VolumeModel]):
    # Note: Multiple volumes are deleted in the same transaction,
    # so long deletion of one volume may block processing other volumes.
    for volume_model in volumes:
        logger.info("Deleting idle volume %s", volume_model.name)
        try:
            await _delete_idle_volume(session, volume_model)
        except Exception:
            logger.exception("Error when deleting idle volume %s", volume_model.name)

        volume_model.deleted = True
        volume_model.deleted_at = get_current_datetime()

        logger.info("Deleted idle volume %s", volume_model.name)

    await session.commit()


async def _delete_idle_volume(session: AsyncSession, volume_model: VolumeModel):
    volume = volume_model_to_volume(volume_model)

    if volume.provisioning_data is None:
        logger.error(
            f"Failed to delete volume {volume_model.name}. volume.provisioning_data is None."
        )
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
