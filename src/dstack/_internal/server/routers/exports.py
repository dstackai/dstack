from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.exports import Export
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.exports import (
    CreateExportRequest,
    DeleteExportRequest,
    UpdateExportRequest,
)
from dstack._internal.server.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.server.services import exports as exports_services
from dstack._internal.server.utils.routers import get_base_api_additional_responses

project_router = APIRouter(
    prefix="/api/project/{project_name}/exports",
    tags=["exports"],
    responses=get_base_api_additional_responses(),
)


@project_router.post("/create", response_model=Export)
async def create_export(
    body: CreateExportRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_project: Annotated[tuple[UserModel, ProjectModel], Depends(ProjectAdmin())],
):
    user, project = user_project
    return await exports_services.create_export(
        session=session,
        project=project,
        user=user,
        name=body.name,
        importer_project_names=body.importer_projects,
        exported_fleet_names=body.exported_fleets,
    )


@project_router.post("/update", response_model=Export)
async def update_export(
    body: UpdateExportRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_project: Annotated[tuple[UserModel, ProjectModel], Depends(ProjectAdmin())],
):
    user, project = user_project
    return await exports_services.update_export(
        session=session,
        project=project,
        user=user,
        name=body.name,
        add_importer_project_names=body.add_importer_projects,
        remove_importer_project_names=body.remove_importer_projects,
        add_exported_fleet_names=body.add_exported_fleets,
        remove_exported_fleet_names=body.remove_exported_fleets,
    )


@project_router.post("/delete")
async def delete_export(
    body: DeleteExportRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_project: Annotated[tuple[UserModel, ProjectModel], Depends(ProjectAdmin())],
):
    _, project = user_project
    await exports_services.delete_export(
        session=session,
        project=project,
        name=body.name,
    )


@project_router.post("/list", response_model=list[Export])
async def list_exports(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_project: Annotated[tuple[UserModel, ProjectModel], Depends(ProjectMember())],
):
    _, project = user_project
    return await exports_services.list_exports(
        session=session,
        project=project,
    )
