from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.instances as instances_services
from dstack._internal.core.models.instances import Instance
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.instances import (
    GetInstanceHealthChecksRequest,
    GetInstanceHealthChecksResponse,
    ListInstancesRequest,
)
from dstack._internal.server.security.permissions import Authenticated, ProjectMember
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

root_router = APIRouter(
    prefix="/api/instances",
    tags=["instances"],
    responses=get_base_api_additional_responses(),
)
project_router = APIRouter(
    prefix="/api/project/{project_name}/instances",
    tags=["instances"],
    responses=get_base_api_additional_responses(),
)


@root_router.post("/list", response_model=List[Instance])
async def list_instances(
    body: ListInstancesRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    """
    Returns all instances visible to user sorted by descending `created_at`.
    `project_names` and `fleet_ids` can be specified as filters.

    The results are paginated. To get the next page, pass `created_at` and `id` of
    the last instance from the previous page as `prev_created_at` and `prev_id`.
    """
    return CustomORJSONResponse(
        await instances_services.list_user_instances(
            session=session,
            user=user,
            project_names=body.project_names,
            fleet_ids=body.fleet_ids,
            only_active=body.only_active,
            prev_created_at=body.prev_created_at,
            prev_id=body.prev_id,
            limit=body.limit,
            ascending=body.ascending,
        )
    )


@project_router.post("/get_instance_health_checks", response_model=GetInstanceHealthChecksResponse)
async def get_instance_health_checks(
    body: GetInstanceHealthChecksRequest,
    session: AsyncSession = Depends(get_session),
    user_project: tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    health_checks = await instances_services.get_instance_health_checks(
        session=session,
        project=project,
        fleet_name=body.fleet_name,
        instance_num=body.instance_num,
        after=body.after,
        before=body.before,
        limit=body.limit,
    )
    return CustomORJSONResponse(GetInstanceHealthChecksResponse(health_checks=health_checks))
