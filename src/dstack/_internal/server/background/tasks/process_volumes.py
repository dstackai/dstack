from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import BackendError, BackendNotAvailable
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import VolumeModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import volumes as volumes_services
from dstack._internal.server.services.volumes import (
    PROCESSING_VOLUMES_IDS,
    PROCESSING_VOLUMES_LOCK,
    get_volume_compute_configuration,
)
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_submitted_volumes():
    async with get_session_ctx() as session:
        async with PROCESSING_VOLUMES_LOCK:
            res = await session.execute(
                select(VolumeModel)
                .where(
                    VolumeModel.status == VolumeStatus.SUBMITTED,
                    VolumeModel.id.not_in(PROCESSING_VOLUMES_IDS),
                )
                .order_by(VolumeModel.last_processed_at.asc())
                .limit(1)
            )
            volume_model = res.scalar()
            if volume_model is None:
                return

            PROCESSING_VOLUMES_IDS.add(volume_model.id)

    try:
        await _process_volume(volume_id=volume_model.id)
    finally:
        PROCESSING_VOLUMES_IDS.remove(volume_model.id)


async def _process_volume(volume_id: UUID):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(VolumeModel)
            .where(VolumeModel.id == volume_id)
            .options(joinedload(VolumeModel.project))
        )
        volume_model = res.scalar_one()
        await _process_submitted_volume(
            session=session,
            volume_model=volume_model,
        )


async def _process_submitted_volume(session: AsyncSession, volume_model: VolumeModel):
    logger.info("Started volume %s provisioning", volume_model.name)

    configuration = volumes_services.get_volume_configuration(volume_model)
    try:
        backend = await backends_services.get_project_backend_by_type_or_error(
            project=volume_model.project, backend_type=configuration.backend
        )
    except BackendNotAvailable:
        volume_model.status = VolumeStatus.FAILED
        volume_model.status_message = "Backend not available"
        volume_model.last_processed_at = get_current_datetime()
        await session.commit()
        return

    compute_configuration = get_volume_compute_configuration(volume_model)

    try:
        vpd = await run_async(
            backend.compute().create_volume,
            configuration=compute_configuration,
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

    volume_model.volume_provisioning_data = vpd.json()
    volume_model.status = VolumeStatus.ACTIVE
    volume_model.last_processed_at = get_current_datetime()
    await session.commit()
