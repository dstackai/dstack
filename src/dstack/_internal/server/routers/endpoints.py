from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.endpoints as endpoints_services
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.endpoint_presets import EndpointPreset, EndpointPresetDetails
from dstack._internal.core.models.endpoints import Endpoint, EndpointPlan
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.endpoint_presets import (
    DeleteEndpointPresetsRequest,
    GetEndpointPresetRequest,
)
from dstack._internal.server.schemas.endpoints import (
    CreateEndpointRequest,
    GetEndpointPlanRequest,
    GetEndpointRequest,
    ListEndpointsRequest,
    StopEndpointsRequest,
)
from dstack._internal.server.security.permissions import Authenticated, ProjectMember
from dstack._internal.server.services.endpoints.presets import (
    endpoint_preset_to_api_details,
    endpoint_preset_to_api_model,
    get_endpoint_preset_service,
)
from dstack._internal.server.services.pipelines import PipelineHinterProtocol, get_pipeline_hinter
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

root_router = APIRouter(
    prefix="/api/endpoints",
    tags=["endpoints"],
    responses=get_base_api_additional_responses(),
)
project_router = APIRouter(prefix="/api/project/{project_name}/endpoints", tags=["endpoints"])


@root_router.post("/list", summary="List endpoints", response_model=List[Endpoint])
async def list_endpoints(
    body: ListEndpointsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    return CustomORJSONResponse(
        await endpoints_services.list_endpoints(
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


@project_router.post("/list", summary="List project endpoints", response_model=List[Endpoint])
async def list_project_endpoints(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    return CustomORJSONResponse(
        await endpoints_services.list_project_endpoints(
            session=session,
            project=project,
        )
    )


@project_router.post("/get", summary="Get endpoint", response_model=Endpoint)
async def get_endpoint(
    body: GetEndpointRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    endpoint = await endpoints_services.get_endpoint_by_name(
        session=session,
        project=project,
        name=body.name,
    )
    if endpoint is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(endpoint)


@project_router.post("/get_plan", summary="Get endpoint apply plan", response_model=EndpointPlan)
async def get_endpoint_plan(
    body: GetEndpointPlanRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    user, project = user_project
    return CustomORJSONResponse(
        await endpoints_services.get_endpoint_plan(
            session=session,
            project=project,
            user=user,
            configuration=body.configuration,
            configuration_path=body.configuration_path,
        )
    )


@project_router.post("/create", summary="Create endpoint", response_model=Endpoint)
async def create_endpoint(
    body: CreateEndpointRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
    pipeline_hinter: PipelineHinterProtocol = Depends(get_pipeline_hinter),
):
    user, project = user_project
    return CustomORJSONResponse(
        await endpoints_services.create_endpoint(
            session=session,
            project=project,
            user=user,
            configuration=body.configuration,
            pipeline_hinter=pipeline_hinter,
        )
    )


@project_router.post("/stop", summary="Stop endpoints")
async def stop_endpoints(
    body: StopEndpointsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
    pipeline_hinter: PipelineHinterProtocol = Depends(get_pipeline_hinter),
):
    user, project = user_project
    await endpoints_services.stop_endpoints(
        session=session,
        project=project,
        names=body.names,
        user=user,
        pipeline_hinter=pipeline_hinter,
    )


@project_router.post(
    "/presets/list", summary="List endpoint presets", response_model=List[EndpointPreset]
)
async def list_endpoint_presets(
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    presets = await get_endpoint_preset_service().list_presets(project.name)
    return CustomORJSONResponse([endpoint_preset_to_api_model(preset) for preset in presets])


@project_router.post(
    "/presets/get", summary="Get endpoint preset", response_model=EndpointPresetDetails
)
async def get_endpoint_preset(
    body: GetEndpointPresetRequest,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    preset = await get_endpoint_preset_service().get_preset(project.name, body.name)
    if preset is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(endpoint_preset_to_api_details(preset))


@project_router.post("/presets/delete", summary="Delete endpoint presets")
async def delete_endpoint_presets(
    body: DeleteEndpointPresetsRequest,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    preset_service = get_endpoint_preset_service()
    try:
        for name in body.names:
            await preset_service.delete_preset(project.name, name)
    except FileNotFoundError:
        raise ResourceNotExistsError()
