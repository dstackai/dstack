from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.fleets as fleets_services
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.fleets import Fleet, FleetPlan
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.fleets import (
    CreateFleetRequest,
    DeleteFleetInstancesRequest,
    DeleteFleetsRequest,
    GetFleetPlanRequest,
    GetFleetRequest,
    ListFleetsRequest,
)
from dstack._internal.server.security.permissions import Authenticated, ProjectMember

root_router = APIRouter(prefix="/api/fleets", tags=["fleets"])
project_router = APIRouter(prefix="/api/project/{project_name}/fleets", tags=["fleets"])


@root_router.post("/list")
async def list_fleets(
    body: ListFleetsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> List[Fleet]:
    return await fleets_services.list_fleets(
        session=session,
        user=user,
        project_name=body.project_name,
        only_active=body.only_active,
        prev_created_at=body.prev_created_at,
        prev_id=body.prev_id,
        limit=body.limit,
        ascending=body.ascending,
    )


@project_router.post("/list")
async def list_project_fleets(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[Fleet]:
    _, project = user_project
    return await fleets_services.list_project_fleets(session=session, project=project)


@project_router.post("/get")
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


@project_router.post("/get_plan")
async def get_plan(
    body: GetFleetPlanRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> FleetPlan:
    user, project = user_project
    plan = await fleets_services.get_plan(
        session=session,
        project=project,
        user=user,
        spec=body.spec,
    )
    return plan


@project_router.post("/create")
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


@project_router.post("/delete")
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


@project_router.post("/delete_instances")
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
