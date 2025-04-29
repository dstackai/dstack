from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.models.gateways as models
import dstack._internal.server.schemas.gateways as schemas
import dstack._internal.server.services.gateways as gateways
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.server.utils.routers import get_base_api_additional_responses

router = APIRouter(
    prefix="/api/project/{project_name}/gateways",
    tags=["gateways"],
    responses=get_base_api_additional_responses(),
)


@router.post("/list")
async def list_gateways(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[models.Gateway]:
    _, project = user_project
    return await gateways.list_project_gateways(session=session, project=project)


@router.post("/get")
async def get_gateway(
    body: schemas.GetGatewayRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> models.Gateway:
    _, project = user_project
    gateway = await gateways.get_gateway_by_name(session=session, project=project, name=body.name)
    if gateway is None:
        raise ResourceNotExistsError()
    return gateway


@router.post("/create")
async def create_gateway(
    body: schemas.CreateGatewayRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> models.Gateway:
    user, project = user_project
    return await gateways.create_gateway(
        session=session,
        user=user,
        project=project,
        configuration=body.configuration,
    )


@router.post("/delete")
async def delete_gateways(
    body: schemas.DeleteGatewaysRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await gateways.delete_gateways(
        session=session,
        project=project,
        gateways_names=body.names,
    )


@router.post("/set_default")
async def set_default_gateway(
    body: schemas.SetDefaultGatewayRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await gateways.set_default_gateway(session=session, project=project, name=body.name)


@router.post("/set_wildcard_domain")
async def set_gateway_wildcard_domain(
    body: schemas.SetWildcardDomainRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> models.Gateway:
    _, project = user_project
    return await gateways.set_gateway_wildcard_domain(
        session=session, project=project, name=body.name, wildcard_domain=body.wildcard_domain
    )
