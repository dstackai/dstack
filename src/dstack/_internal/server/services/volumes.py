import asyncio
import uuid
from datetime import timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends import BACKENDS_WITH_VOLUMES_SUPPORT
from dstack._internal.core.errors import (
    BackendNotAvailable,
    ResourceExistsError,
    ServerClientError,
)
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeAttachmentData,
    VolumeConfiguration,
    VolumeProvisioningData,
    VolumeStatus,
)
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.server.models import ProjectModel, VolumeModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.utils.common import run_async, wait_to_lock_many
from dstack._internal.utils import common, random_names
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


PROCESSING_VOLUMES_LOCK = asyncio.Lock()
PROCESSING_VOLUMES_IDS = set()


async def list_project_volumes(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
) -> List[Volume]:
    volume_models = await list_project_volume_models(session=session, project=project, names=names)
    return [volume_model_to_volume(v) for v in volume_models]


async def list_project_volume_models(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
    include_deleted: bool = False,
) -> List[VolumeModel]:
    filters = [
        VolumeModel.project_id == project.id,
    ]
    if names is not None:
        filters.append(VolumeModel.name.in_(names))
    if not include_deleted:
        filters.append(VolumeModel.deleted == False)
    res = await session.execute(select(VolumeModel).where(*filters))
    return list(res.scalars().all())


async def get_volume_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[Volume]:
    volume_model = await get_project_volume_model_by_name(
        session=session, project=project, name=name
    )
    if volume_model is None:
        return None
    return volume_model_to_volume(volume_model)


async def get_project_volume_model_by_name(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    include_deleted: bool = False,
) -> Optional[VolumeModel]:
    filters = [
        VolumeModel.name == name,
        VolumeModel.project_id == project.id,
    ]
    if not include_deleted:
        filters.append(VolumeModel.deleted == False)
    res = await session.execute(select(VolumeModel).where(*filters))
    return res.scalar_one_or_none()


async def create_volume(
    session: AsyncSession,
    project: ProjectModel,
    configuration: VolumeConfiguration,
) -> Volume:
    _validate_volume_configuration(configuration)

    if configuration.name is not None:
        volume_model = await get_project_volume_model_by_name(
            session=session,
            project=project,
            name=configuration.name,
        )
        if volume_model is not None:
            raise ResourceExistsError()
    else:
        configuration.name = await generate_volume_name(session=session, project=project)

    volume_model = VolumeModel(
        id=uuid.uuid4(),
        name=configuration.name,
        project=project,
        status=VolumeStatus.SUBMITTED,
        configuration=configuration.json(),
    )
    session.add(volume_model)
    await session.commit()
    await session.refresh(volume_model)
    return volume_model_to_volume(volume_model)


async def delete_volumes(session: AsyncSession, project: ProjectModel, names: List[str]):
    res = await session.execute(
        select(VolumeModel).where(
            VolumeModel.project_id == project.id,
            VolumeModel.name.in_(names),
            VolumeModel.deleted == False,
        )
    )
    volume_models = res.scalars().all()
    volumes_ids = sorted([v.id for v in volume_models])
    logger.info("Deleting volumes: %s", [v.name for v in volume_models])
    await wait_to_lock_many(PROCESSING_VOLUMES_LOCK, PROCESSING_VOLUMES_IDS, volumes_ids)
    try:
        # Refetch after lock
        res = await session.execute(
            select(VolumeModel)
            .where(
                VolumeModel.project_id == project.id,
                VolumeModel.name.in_(names),
                VolumeModel.deleted == False,
            )
            .options(joinedload(VolumeModel.instances))
            .execution_options(populate_existing=True)
        )
        volume_models = res.scalars().unique().all()
        for volume_model in volume_models:
            if len(volume_model.instances) > 0:
                raise ServerClientError(
                    f"Failed to delete volume {volume_model.name}. Volume is in use."
                )
        for volume_model in volume_models:
            try:
                await _delete_volume(session=session, project=project, volume_model=volume_model)
            except Exception:
                logger.exception("Error when deleting volume %s", volume_model.name)
        await session.execute(
            update(VolumeModel)
            .where(
                VolumeModel.project_id == project.id,
                VolumeModel.id.in_(volumes_ids),
            )
            .values(
                deleted=True,
                deleted_at=common.get_current_datetime(),
            )
        )
        await session.commit()
    finally:
        PROCESSING_VOLUMES_IDS.difference_update(volumes_ids)


def volume_model_to_volume(volume_model: VolumeModel) -> Volume:
    configuration = get_volume_configuration(volume_model)
    vpd = get_volume_provisioning_data(volume_model)
    vad = get_volume_attachment_data(volume_model)
    # Initially VolumeProvisionigData lacked backend
    if vpd is not None and vpd.backend is None:
        vpd.backend = configuration.backend
    return Volume(
        name=volume_model.name,
        project_name=volume_model.project.name,
        configuration=configuration,
        external=configuration.volume_id is not None,
        created_at=volume_model.created_at.replace(tzinfo=timezone.utc),
        status=volume_model.status,
        status_message=volume_model.status_message,
        volume_id=vpd.volume_id if vpd is not None else None,
        provisioning_data=vpd,
        attachment_data=vad,
        volume_model_id=volume_model.id,
    )


def get_volume_configuration(volume_model: VolumeModel) -> VolumeConfiguration:
    return VolumeConfiguration.__response__.parse_raw(volume_model.configuration)


def get_volume_provisioning_data(volume_model: VolumeModel) -> Optional[VolumeProvisioningData]:
    if volume_model.volume_provisioning_data is None:
        return None
    return VolumeProvisioningData.__response__.parse_raw(volume_model.volume_provisioning_data)


def get_volume_attachment_data(volume_model: VolumeModel) -> Optional[VolumeAttachmentData]:
    if volume_model.volume_attachment_data is None:
        return None
    return VolumeAttachmentData.__response__.parse_raw(volume_model.volume_attachment_data)


async def generate_volume_name(session: AsyncSession, project: ProjectModel) -> str:
    volume_models = await list_project_volume_models(session=session, project=project)
    names = {v.name for v in volume_models}
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


def _validate_volume_configuration(configuration: VolumeConfiguration):
    if configuration.volume_id is None and configuration.size is None:
        raise ServerClientError("Volume must specify either volume_id or size")
    if configuration.backend not in BACKENDS_WITH_VOLUMES_SUPPORT:
        raise ServerClientError(
            f"Volumes are not supported for {configuration.backend.value} backend. "
            f"Supported backends: {[b.value for b in BACKENDS_WITH_VOLUMES_SUPPORT]}."
        )
    if configuration.name is not None:
        validate_dstack_resource_name(configuration.name)


async def _delete_volume(session: AsyncSession, project: ProjectModel, volume_model: VolumeModel):
    volume = volume_model_to_volume(volume_model)
    if volume.external:
        return

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

    await run_async(
        backend.compute().delete_volume,
        volume=volume,
    )
