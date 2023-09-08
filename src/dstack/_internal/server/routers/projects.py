from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import Authenticated, ProjectMember

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/list")
async def list_projects(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> List[Project]:
    return await users.list_users(session=session)


@router.post("/{project_name}/get")
async def get_project(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Project:
    _, project = user_project
    project_info = await ProjectManager.get_project_info(project)
    return project_info
