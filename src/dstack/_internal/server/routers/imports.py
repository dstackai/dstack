from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.imports import Import
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import imports as imports_services
from dstack._internal.server.utils.routers import get_base_api_additional_responses

project_router = APIRouter(
    prefix="/api/project/{project_name}/imports",
    tags=["imports"],
    responses=get_base_api_additional_responses(),
)


@project_router.post("/list", response_model=list[Import])
async def list_imports(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_project: Annotated[tuple[UserModel, ProjectModel], Depends(ProjectMember())],
):
    _, project = user_project
    return await imports_services.list_imports(
        session=session,
        project=project,
    )
