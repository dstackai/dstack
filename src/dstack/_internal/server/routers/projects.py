from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.projects import Project
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.projects import (
    CreateProjectRequest,
    DeleteProjectsRequest,
    SetProjectMembersRequest,
)
from dstack._internal.server.security.permissions import Authenticated, ProjectAdmin, ProjectMember
from dstack._internal.server.services import projects

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/list")
async def list_projects(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> List[Project]:
    return await projects.list_user_projects(session=session, user=user)


@router.post("/create")
async def create_project(
    body: CreateProjectRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> Project:
    return await projects.create_project(
        session=session,
        user=user,
        project_name=body.project_name,
    )


@router.post("/delete")
async def delete_projects(
    body: DeleteProjectsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    await projects.delete_projects(
        session=session,
        user=user,
        projects_names=body.projects_names,
    )


@router.post("/{project_name}/get")
async def get_project(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Project:
    _, project = user_project
    return projects.project_model_to_project(project)


@router.post(
    "/{project_name}/set_members",
)
async def set_project_members(
    body: SetProjectMembersRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> Project:
    _, project = user_project
    await projects.set_project_members(
        session=session,
        project=project,
        members=body.members,
    )
    await session.refresh(project)
    return projects.project_model_to_project(project)
