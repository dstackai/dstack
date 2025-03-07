from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.errors import BackendError, BackendNotAvailable
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    InstanceModel,
    ProjectModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import volumes as volumes_services
from dstack._internal.server.services.locking import get_locker
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_submitted_volumes():
    lock, lockset = get_locker().get_lockset(VolumeModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(VolumeModel)
                .where(
                    VolumeModel.status == VolumeStatus.SUBMITTED,
                    VolumeModel.id.not_in(lockset),
                )
                .order_by(VolumeModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            volume_model = res.scalar()
            if volume_model is None:
                return
            lockset.add(volume_model.id)
        try:
            volume_model_id = volume_model.id
            await _process_submitted_volume(session=session, volume_model=volume_model)
        finally:
            lockset.difference_update([volume_model_id])


async def _process_submitted_volume(session: AsyncSession, volume_model: VolumeModel):
    logger.info("Started submitted volume %s processing", volume_model.name)
    # Refetch to load related attributes.
    # joinedload produces LEFT OUTER JOIN that can't be used with FOR UPDATE.
    res = await session.execute(
        select(VolumeModel)
        .where(VolumeModel.id == volume_model.id)
        .options(joinedload(VolumeModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(VolumeModel.user))
        .options(
            joinedload(VolumeModel.attachments)
            .joinedload(VolumeAttachmentModel.instance)
            .joinedload(InstanceModel.fleet)
        )
        .execution_options(populate_existing=True)
    )
    volume_model = res.unique().scalar_one()
    volume = volumes_services.volume_model_to_volume(volume_model)
    try:
        backend = await backends_services.get_project_backend_by_type_or_error(
            project=volume_model.project,
            backend_type=volume.configuration.backend,
            overrides=True,
        )
    except BackendNotAvailable:
        logger.error(
            "Failed to process volume %s. Backend %s not available.",
            volume.name,
            volume.configuration.backend.value,
        )
        volume_model.status = VolumeStatus.FAILED
        volume_model.status_message = "Backend not available"
        volume_model.last_processed_at = get_current_datetime()
        await session.commit()
        return

    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)
    try:
        if volume.configuration.volume_id is not None:
            logger.info("Registering external volume %s", volume_model.name)
            vpd = await run_async(
                compute.register_volume,
                volume=volume,
            )
        else:
            logger.info("Provisioning new volume %s", volume_model.name)
            vpd = await run_async(
                compute.create_volume,
                volume=volume,
            )
    except BackendError as e:
        logger.info("Failed to create volume %s: %s", volume_model.name, repr(e))
        volume_model.status = VolumeStatus.FAILED
        status_message = f"Backend error: {repr(e)}"
        if len(e.args) > 0:
            status_message = str(e.args[0])
        volume_model.status_message = status_message
        volume_model.last_processed_at = get_current_datetime()
        await session.commit()
        return
    except Exception as e:
        logger.exception("Got exception when creating volume %s", volume_model.name)
        volume_model.status = VolumeStatus.FAILED
        volume_model.status_message = f"Unexpected error: {repr(e)}"
        volume_model.last_processed_at = get_current_datetime()
        await session.commit()
        return

    logger.info("Added new volume %s", volume_model.name)

    # Provisioned volumes marked as active since they become available almost immediately in AWS
    # TODO: Consider checking volume state
    volume_model.volume_provisioning_data = vpd.json()
    volume_model.status = VolumeStatus.ACTIVE
    volume_model.last_processed_at = get_current_datetime()
    await session.commit()
