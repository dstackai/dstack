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
    ListVolumesRequest,
)
from dstack._internal.server.security.permissions import Authenticated, ProjectMember
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

root_router = APIRouter(
    prefix="/api/volumes",
    tags=["volumes"],
    responses=get_base_api_additional_responses(),
)
project_router = APIRouter(prefix="/api/project/{project_name}/volumes", tags=["volumes"])


@root_router.post("/list", response_model=List[Volume])
async def list_volumes(
    body: ListVolumesRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    """
    Returns all volumes visible to user sorted by descending `created_at`.
    `project_name` and `only_active` can be specified as filters.

    The results are paginated. To get the next page, pass `created_at` and `id` of
    the last fleet from the previous page as `prev_created_at` and `prev_id`.
    """
    return CustomORJSONResponse(
        await volumes_services.list_volumes(
            session=session,
            user=user,
            project_name=body.project_name,
            only_active=body.only_active,
            prev_created_at=body.prev_created_at,
            prev_id=body.prev_id,
            limit=body.limit,
            ascending=body.ascending,
        )
    )


@project_router.post("/list", response_model=List[Volume])
async def list_project_volumes(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Returns all volumes in the project.
    """
    _, project = user_project
    return CustomORJSONResponse(
        await volumes_services.list_project_volumes(session=session, project=project)
    )


@project_router.post("/get", response_model=Volume)
async def get_volume(
    body: GetVolumeRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Returns a volume given a volume name.
    """
    _, project = user_project
    volume = await volumes_services.get_volume_by_name(
        session=session, project=project, name=body.name
    )
    if volume is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(volume)


@project_router.post("/create", response_model=Volume)
async def create_volume(
    body: CreateVolumeRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Creates a volume given a volume configuration.
    """
    user, project = user_project
    return CustomORJSONResponse(
        await volumes_services.create_volume(
            session=session,
            project=project,
            user=user,
            configuration=body.configuration,
        )
    )


@project_router.post("/delete")
async def delete_volumes(
    body: DeleteVolumesRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Deletes one or more volumes.
    """
    _, project = user_project
    await volumes_services.delete_volumes(session=session, project=project, names=body.names)
