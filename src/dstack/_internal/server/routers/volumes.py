from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.volumes as volumes_services
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.volumes import Volume
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.volumes import (
    CreateVolumeRequest,
    DeleteVolumesRequest,
    GetVolumeRequest,
)
from dstack._internal.server.security.permissions import ProjectMember

router = APIRouter(prefix="/api/project/{project_name}/volumes", tags=["volumes"])


@router.post("/list")
async def list_volumes(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[Volume]:
    _, project = user_project
    return await volumes_services.list_project_volumes(session=session, project=project)


@router.post("/get")
async def get_volume(
    body: GetVolumeRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Volume:
    _, project = user_project
    volume = await volumes_services.get_volume_by_name(
        session=session, project=project, name=body.name
    )
    if volume is None:
        raise ResourceNotExistsError()
    return volume


@router.post("/create")
async def create_volume(
    body: CreateVolumeRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Volume:
    _, project = user_project
    return await volumes_services.create_volume(
        session=session,
        project=project,
        configuration=body.configuration,
    )


@router.post("/delete")
async def delete_volumes(
    body: DeleteVolumesRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    await volumes_services.delete_volumes(session=session, project=project, names=body.names)
