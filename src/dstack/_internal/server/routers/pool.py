from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.models.pool as models
import dstack._internal.server.schemas.pool as schemas
import dstack._internal.server.services.pool as pool
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import ProjectAdmin, ProjectMember

router = APIRouter(prefix="/api/project/{project_name}/pool", tags=["pool"])


@router.post("/list")
async def list_pool(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[models.Pool]:
    _, project = user_project
    return await pool.list_project_pool(session=session, project=project)


@router.post("/delete")
async def delete_pool(
    body: schemas.DeletePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await pool.delete_pool(session=session, project=project, pool_name=body.name)


@router.post("/create")
async def create_pool(
    body: schemas.CreatePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await pool.create_pool_model(session=session, project=project, name=body.name)


@router.post("/show")
async def how_pool(
    body: schemas.CreatePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    return await pool.show_pool(session, project, pool_name=body.name)
