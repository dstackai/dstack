from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.fleets as fleets_services
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.fleets import Fleet, FleetPlan
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.fleets import (
    ApplyFleetPlanRequest,
    CreateFleetRequest,
    DeleteFleetInstancesRequest,
    DeleteFleetsRequest,
    GetFleetPlanRequest,
    GetFleetRequest,
    ListFleetsRequest,
)
from dstack._internal.server.security.permissions import Authenticated, ProjectMember
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

root_router = APIRouter(
    prefix="/api/fleets",
    tags=["fleets"],
    responses=get_base_api_additional_responses(),
)
project_router = APIRouter(
    prefix="/api/project/{project_name}/fleets",
    tags=["fleets"],
    responses=get_base_api_additional_responses(),
)


@root_router.post("/list", response_model=List[Fleet])
async def list_fleets(
    body: ListFleetsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    """
    Returns all fleets and instances within them visible to user sorted by descending `created_at`.
    `project_name` and `only_active` can be specified as filters.

    The results are paginated. To get the next page, pass `created_at` and `id` of
    the last fleet from the previous page as `prev_created_at` and `prev_id`.
    """
    return CustomORJSONResponse(
        await fleets_services.list_fleets(
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


@project_router.post("/list", response_model=List[Fleet])
async def list_project_fleets(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Returns all fleets in the project.
    """
    _, project = user_project
    return CustomORJSONResponse(
        await fleets_services.list_project_fleets(session=session, project=project)
    )


@project_router.post("/get", response_model=Fleet)
async def get_fleet(
    body: GetFleetRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Returns a fleet given `name` or `id`.
    If given `name`, does not return deleted fleets.
    If given `id`, returns deleted fleets.
    """
    _, project = user_project
    fleet = await fleets_services.get_fleet(
        session=session, project=project, name=body.name, fleet_id=body.id
    )
    if fleet is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(fleet)


@project_router.post("/get_plan", response_model=FleetPlan)
async def get_plan(
    body: GetFleetPlanRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Returns a fleet plan for the given fleet configuration.
    """
    user, project = user_project
    plan = await fleets_services.get_plan(
        session=session,
        project=project,
        user=user,
        spec=body.spec,
    )
    return CustomORJSONResponse(plan)


@project_router.post("/apply", response_model=Fleet)
async def apply_plan(
    body: ApplyFleetPlanRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Creates a new fleet or updates an existing fleet.
    Errors if the expected current resource from the plan does not match the current resource.
    Use `force: true` to apply even if the current resource does not match.
    """
    user, project = user_project
    return CustomORJSONResponse(
        await fleets_services.apply_plan(
            session=session,
            user=user,
            project=project,
            plan=body.plan,
            force=body.force,
        )
    )


@project_router.post("/create", response_model=Fleet)
async def create_fleet(
    body: CreateFleetRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Creates a fleet given a fleet configuration.
    """
    user, project = user_project
    return CustomORJSONResponse(
        await fleets_services.create_fleet(
            session=session,
            project=project,
            user=user,
            spec=body.spec,
        )
    )


@project_router.post("/delete")
async def delete_fleets(
    body: DeleteFleetsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Deletes one or more fleets.
    """
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
    """
    Deletes one or more instances within the fleet.
    """
    user, project = user_project
    await fleets_services.delete_fleets(
        session=session,
        project=project,
        user=user,
        names=[body.name],
        instance_nums=body.instance_nums,
    )
