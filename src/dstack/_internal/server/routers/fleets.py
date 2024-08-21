from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.fleets as fleets_services
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.fleets import Fleet
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.fleets import (
    CreateFleetRequest,
    DeleteFleetInstancesRequest,
    DeleteFleetsRequest,
    GetFleetRequest,
)
from dstack._internal.server.security.permissions import ProjectMember

router = APIRouter(prefix="/api/project/{project_name}/fleets", tags=["fleets"])


@router.post("/list")
async def list_fleets(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[Fleet]:
    _, project = user_project
    return await fleets_services.list_project_fleets(session=session, project=project)


@router.post("/get")
async def get_fleet(
    body: GetFleetRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Fleet:
    _, project = user_project
    fleet = await fleets_services.get_fleet_by_name(
        session=session, project=project, name=body.name
    )
    if fleet is None:
        raise ResourceNotExistsError()
    return fleet


@router.post("/create")
async def create_fleet(
    body: CreateFleetRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Fleet:
    user, project = user_project
    return await fleets_services.create_fleet(
        session=session,
        project=project,
        user=user,
        spec=body.spec,
    )


@router.post("/delete")
async def delete_fleets(
    body: DeleteFleetsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    user, project = user_project
    await fleets_services.delete_fleets(
        session=session,
        project=project,
        user=user,
        names=body.names,
    )


@router.post("/delete_instances")
async def delete_fleet_instances(
    body: DeleteFleetInstancesRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    user, project = user_project
    await fleets_services.delete_fleets(
        session=session,
        project=project,
        user=user,
        names=[body.name],
        instance_nums=body.instance_nums,
    )
