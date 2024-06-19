import asyncio
from datetime import timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendNotAvailable, ResourceExistsError
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeComputeConfiguration,
    VolumeConfiguration,
    VolumeProvisioningData,
    VolumeStatus,
)
from dstack._internal.server.models import ProjectModel, VolumeModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.utils.common import run_async, wait_to_lock_many
from dstack._internal.utils import common, random_names
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


PROCESSING_VOLUMES_LOCK = asyncio.Lock()
PROCESSING_VOLUMES_IDS = set()


async def list_project_volumes(session: AsyncSession, project: ProjectModel) -> List[Volume]:
    volume_models = await list_project_volume_models(session=session, project=project)
    return [volume_model_to_volume(v) for v in volume_models]


async def list_project_volume_models(
    session: AsyncSession, project: ProjectModel, include_deleted: bool = False
) -> List[VolumeModel]:
    filters = [
        VolumeModel.project_id == project.id,
    ]
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
    if configuration.name is not None:
        volume_model = await get_project_volume_model_by_name(
            session=session,
            project=project,
            name=configuration.name,
        )
        if volume_model is not None:
            raise ResourceExistsError()

    if configuration.name is None:
        configuration.name = await generate_volume_name(session=session, project=project)

    volume_model = VolumeModel(
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
    volumes_ids = [v.id for v in volume_models]
    # TODO: check for volumes in use. refetch with lock.
    await wait_to_lock_many(PROCESSING_VOLUMES_LOCK, PROCESSING_VOLUMES_IDS, volumes_ids)
    try:
        tasks = []
        for volume_model in volume_models:
            tasks.append(
                _delete_volume(session=session, project=project, volume_model=volume_model)
            )
        terminate_results = await asyncio.gather(*tasks, return_exceptions=True)
        for volume_model, error in zip(volume_models, terminate_results):
            if isinstance(error, Exception):
                logger.exception(
                    "Error when deleting volume %s",
                    volume_model.name,
                    exc_info=(type(error), error, error.__traceback__),
                )
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
    return Volume(
        name=volume_model.name,
        configuration=configuration,
        created_at=volume_model.created_at.replace(tzinfo=timezone.utc),
        status=volume_model.status,
        status_message=volume_model.status_message,
        volume_id=vpd.volume_id if vpd is not None else None,
    )


def get_volume_compute_configuration(volume_model: VolumeModel) -> VolumeComputeConfiguration:
    configuration = get_volume_configuration(volume_model)
    return VolumeComputeConfiguration(
        name=volume_model.name,
        project_name=volume_model.project.name,
        backend=configuration.backend,
        size_gb=int(configuration.size),
        volume_id=configuration.volume_id,
        region=configuration.region,
    )


def get_volume_configuration(volume_model: VolumeModel) -> VolumeConfiguration:
    return VolumeConfiguration.__response__.parse_raw(volume_model.configuration)


def get_volume_provisioning_data(volume_model: VolumeModel) -> Optional[VolumeProvisioningData]:
    if volume_model.volume_provisioning_data is None:
        return None
    return VolumeProvisioningData.__response__.parse_raw(volume_model.volume_provisioning_data)


async def generate_volume_name(session: AsyncSession, project: ProjectModel) -> str:
    volume_models = await list_project_volume_models(session=session, project=project)
    names = {v.name for v in volume_models}
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


async def _delete_volume(session: AsyncSession, project: ProjectModel, volume_model: VolumeModel):
    configuration = get_volume_configuration(volume_model)
    try:
        backend = await backends_services.get_project_backend_by_type_or_error(
            project=volume_model.project, backend_type=configuration.backend
        )
    except BackendNotAvailable:
        logger.error(
            f"Failed to delete volume {volume_model.name}. Backend {configuration.backend} not available."
        )
        return

    vpd = get_volume_provisioning_data(volume_model)
    if vpd is None:
        logger.error(
            f"Failed to delete volume {volume_model.name}. Volume provisioning data is None."
        )
        return

    await run_async(
        backend.compute().delete_volume,
        volume_id=vpd.volume_id,
        configuration=get_volume_compute_configuration(volume_model),
        backend_data=vpd.backend_data,
    )
