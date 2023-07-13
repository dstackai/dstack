from typing import List, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack._internal.hub.db.models import Project, User
from dstack._internal.hub.models import (
    Member,
    ProjectConfigWithCredsPartial,
    ProjectDelete,
    ProjectInfo,
    ProjectInfoWithCreds,
    ProjectValues,
)
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.routers.util import error_detail, get_backend_configurator, get_project
from dstack._internal.hub.security.permissions import (
    Authenticated,
    ProjectAdmin,
    ProjectMember,
    ensure_user_project_admin,
)
from dstack._internal.hub.services.backends.base import BackendConfigError
from dstack._internal.hub.services.backends.cache import clear_backend_cache
from dstack._internal.hub.utils.common import run_async

router = APIRouter(prefix="/api/projects", tags=["project"])


@router.post("/backends/values")
async def get_backend_config_values(
    config: ProjectConfigWithCredsPartial = Body(),
    user: User = Depends(Authenticated()),
) -> ProjectValues:
    configurator = get_backend_configurator(config.__root__.type)
    try:
        result = await run_async(configurator.configure_project, config.__root__)
    except BackendConfigError as e:
        _error_response_on_config_error(e, path_to_config=[])
    return result


@router.get(
    "/list",
)
async def list_projects(user: User = Depends(Authenticated())) -> List[ProjectInfo]:
    return await ProjectManager.list_project_info()


@router.post("")
async def create_project(
    project_info: ProjectInfoWithCreds, user: User = Depends(Authenticated())
) -> ProjectInfoWithCreds:
    project = await ProjectManager.get(name=project_info.project_name)
    if project is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                error_detail(
                    "Project exists", code="project_name_not_unique", loc=["project_name"]
                )
            ],
        )
    configurator = get_backend_configurator(project_info.backend.__root__.type)
    try:
        await run_async(configurator.configure_project, project_info.backend.__root__)
        await ProjectManager.create_project_from_info(user=user, project_info=project_info)
    except BackendConfigError as e:
        _error_response_on_config_error(e, path_to_config=["backend"])
    return project_info


@router.delete("")
async def delete_projects(body: ProjectDelete, user: User = Depends(Authenticated())):
    for project_name in body.projects:
        project = await get_project(project_name)
        await ensure_user_project_admin(user, project)
        await ProjectManager.delete(project_name)
        clear_backend_cache(project_name)


@router.post(
    "/{project_name}/members",
)
async def set_project_members(
    body: List[Member] = Body(), user_project: Tuple[User, Project] = Depends(ProjectAdmin())
):
    _, project = user_project
    await ProjectManager.set_members(project=project, members=body)


@router.get("/{project_name}/config_info")
async def get_project_config_info(
    user_project: Tuple[User, Project] = Depends(ProjectAdmin())
) -> ProjectInfoWithCreds:
    _, project = user_project
    project_info = await ProjectManager.get_project_info_with_creds(project)
    return project_info


@router.get("/{project_name}")
async def get_project_info(
    user_project: Tuple[User, Project] = Depends(ProjectMember())
) -> ProjectInfo:
    _, project = user_project
    project_info = await ProjectManager.get_project_info(project)
    return project_info


@router.patch("/{project_name}")
async def update_project(
    project_info: ProjectInfoWithCreds = Body(),
    user_project: Tuple[User, Project] = Depends(ProjectAdmin()),
) -> ProjectInfoWithCreds:
    configurator = get_backend_configurator(project_info.backend.__root__.type)
    try:
        await run_async(configurator.configure_project, project_info.backend.__root__)
    except BackendConfigError as e:
        _error_response_on_config_error(e, path_to_config=["backend"])
    await ProjectManager.update_project_from_info(project_info)
    clear_backend_cache(project_info.project_name)
    return project_info


def _error_response_on_config_error(e: BackendConfigError, path_to_config: List[str]):
    if len(e.fields) > 0:
        error_details = [
            error_detail(e.message, code=e.code, loc=path_to_config + f) for f in e.fields
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_details,
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=[error_detail(e.message, code=e.code)],
    )
