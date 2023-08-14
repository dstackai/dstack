from typing import List, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack._internal.hub.db.models import Project, User
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.routers.util import error_detail, get_project
from dstack._internal.hub.schemas import Member, ProjectCreate, ProjectInfo, ProjectsDelete
from dstack._internal.hub.security.permissions import (
    Authenticated,
    ProjectAdmin,
    ProjectMember,
    ensure_user_project_admin,
)
from dstack._internal.hub.services.backends.cache import clear_backend_cache

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post(
    "/list",
)
async def list_projects(user: User = Depends(Authenticated())) -> List[ProjectInfo]:
    return await ProjectManager.list_project_info()


@router.post("/create")
async def create_project(
    body: ProjectCreate, user: User = Depends(Authenticated())
) -> ProjectInfo:
    project = await ProjectManager.get(name=body.project_name)
    if project is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                error_detail(
                    "Project exists", code="project_name_not_unique", loc=["project_name"]
                )
            ],
        )
    await ProjectManager.create(user=user, project_name=body.project_name, members=body.members)
    project = await ProjectManager.get(name=body.project_name)
    return await ProjectManager.get_project_info(project)


@router.post("/delete")
async def delete_projects(body: ProjectsDelete, user: User = Depends(Authenticated())):
    for project_name in body.projects:
        project = await get_project(project_name)
        await ensure_user_project_admin(user, project)
        await ProjectManager.delete(project_name)
        clear_backend_cache(project_name)


@router.post("/{project_name}/info")
async def get_project_info(
    user_project: Tuple[User, Project] = Depends(ProjectMember())
) -> ProjectInfo:
    _, project = user_project
    project_info = await ProjectManager.get_project_info(project)
    return project_info


@router.post(
    "/{project_name}/members",
)
async def set_project_members(
    body: List[Member] = Body(), user_project: Tuple[User, Project] = Depends(ProjectAdmin())
):
    _, project = user_project
    await ProjectManager.set_members(project=project, members=body)
