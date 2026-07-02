from typing import Annotated, List, Optional, Tuple

from fastapi import APIRouter, Depends
from packaging.version import Version
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.models.gateways as models
import dstack._internal.server.schemas.gateways as schemas
import dstack._internal.server.services.gateways as gateways
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.common import EntityReference
from dstack._internal.server.compatibility.gateways import patch_gateway, patch_gateway_plan
from dstack._internal.server.db import get_session
from dstack._internal.server.deps import Project
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import (
    Authenticated,
    ProjectAdmin,
    ProjectMemberOrPublicAccess,
    check_can_access_gateway,
)
from dstack._internal.server.services.pipelines import PipelineHinterProtocol, get_pipeline_hinter
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
    get_client_version,
)

router = APIRouter(
    prefix="/api/project/{project_name}/gateways",
    tags=["gateways"],
    responses=get_base_api_additional_responses(),
)


@router.post("/list", summary="List gateways", response_model=List[models.Gateway])
async def list_gateways(
    body: Optional[schemas.ListGatewaysRequest] = None,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMemberOrPublicAccess()),
    client_version: Optional[Version] = Depends(get_client_version),
):
    _, project = user_project
    if body is None:
        body = schemas.ListGatewaysRequest()
    gateway_list = await gateways.list_project_gateways(
        session=session,
        project=project,
        include_imported=body.include_imported,
    )
    for gateway in gateway_list:
        patch_gateway(gateway, client_version)
    return CustomORJSONResponse(gateway_list)


@router.post("/get", summary="Get gateway", response_model=models.Gateway)
async def get_gateway(
    body: schemas.GetGatewayRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
    project: ProjectModel = Depends(Project()),
    client_version: Optional[Version] = Depends(get_client_version),
):
    await check_can_access_gateway(
        session=session, user=user, gateway_project=project, gateway_name=body.name
    )
    gateway = await gateways.get_gateway_by_name(session=session, project=project, name=body.name)
    if gateway is None:
        raise ResourceNotExistsError()
    patch_gateway(gateway, client_version)
    return CustomORJSONResponse(gateway)


@router.post("/get_plan", summary="Get gateway plan", response_model=models.GatewayPlan)
async def get_plan(
    body: schemas.GetGatewayPlanRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_project: Annotated[tuple[UserModel, ProjectModel], Depends(ProjectAdmin())],
    client_version: Annotated[Optional[Version], Depends(get_client_version)],
):
    """
    Returns a gateway plan for the given gateway spec.
    This is an optional step before calling `/apply`.
    """
    user, project = user_project
    plan = await gateways.get_plan(
        session=session,
        project=project,
        user=user,
        spec=body.spec,
    )
    patch_gateway_plan(plan, client_version)
    return CustomORJSONResponse(plan)


@router.post("/apply", summary="Apply gateway plan", response_model=models.Gateway)
async def apply_plan(
    body: schemas.ApplyGatewayPlanRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_project: Annotated[tuple[UserModel, ProjectModel], Depends(ProjectAdmin())],
    pipeline_hinter: Annotated[PipelineHinterProtocol, Depends(get_pipeline_hinter)],
    client_version: Annotated[Optional[Version], Depends(get_client_version)],
):
    """
    Creates a new gateway or updates an existing gateway in-place.
    """
    user, project = user_project
    gateway = await gateways.apply_plan(
        session=session,
        user=user,
        project=project,
        plan=body.plan,
        force=body.force,
        pipeline_hinter=pipeline_hinter,
    )
    patch_gateway(gateway, client_version)
    return CustomORJSONResponse(gateway)


@router.post("/create", summary="Create gateway", response_model=models.Gateway, deprecated=True)
async def create_gateway(
    body: schemas.CreateGatewayRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
    pipeline_hinter: PipelineHinterProtocol = Depends(get_pipeline_hinter),
    client_version: Optional[Version] = Depends(get_client_version),
):
    """
    Deprecated in favor of `/apply`.
    """
    user, project = user_project
    gateway = await gateways.create_gateway(
        session=session,
        user=user,
        project=project,
        configuration=body.configuration,
        pipeline_hinter=pipeline_hinter,
    )
    patch_gateway(gateway, client_version)
    return CustomORJSONResponse(gateway)


@router.post("/delete", summary="Delete gateways")
async def delete_gateways(
    body: schemas.DeleteGatewaysRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    user, project = user_project
    await gateways.delete_gateways(
        session=session,
        project=project,
        gateways_names=body.names,
        user=user,
    )


@router.post("/set_default", summary="Set default gateway")
async def set_default_gateway(
    body: schemas.SetDefaultGatewayRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    user, project = user_project
    await gateways.set_default_gateway(
        session=session,
        project=project,
        ref=EntityReference(name=body.name, project=body.gateway_project),
        user=user,
    )


@router.post(
    "/set_wildcard_domain",
    summary="Set wildcard domain",
    response_model=models.Gateway,
    deprecated=True,
)
async def set_gateway_wildcard_domain(
    body: schemas.SetWildcardDomainRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
    client_version: Optional[Version] = Depends(get_client_version),
):
    """
    Deprecated in favor of `/apply` (in-place update).
    """
    user, project = user_project
    gateway = await gateways.set_gateway_wildcard_domain(
        session=session,
        project=project,
        name=body.name,
        wildcard_domain=body.wildcard_domain,
        user=user,
    )
    patch_gateway(gateway, client_version)
    return CustomORJSONResponse(gateway)
