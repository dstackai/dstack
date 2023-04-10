import asyncio
from typing import List, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack.api.backend import dict_backends
from dstack.backend.base import Backend
from dstack.core.error import HubConfigError
from dstack.hub.db.models import Project, User
from dstack.hub.models import (
    Member,
    ProjectConfigWithCredsPartial,
    ProjectDelete,
    ProjectInfo,
    ProjectInfoWithCreds,
    ProjectValues,
)
from dstack.hub.repository.projects import ProjectManager
from dstack.hub.routers.cache import clear_backend_cache
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import (
    Authenticated,
    ProjectAdmin,
    ProjectMember,
    ensure_user_project_admin,
)

router = APIRouter(prefix="/api/projects", tags=["project"])


@router.post("/backends/values")
async def get_backend_config_values(
    config: ProjectConfigWithCredsPartial = Body(),
    user: User = Depends(Authenticated()),
) -> ProjectValues:
    backend = _get_backend(config.__root__.type)
    configurator = backend.get_configurator()
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None, configurator.configure_hub, config.__root__.dict()
        )
    except HubConfigError as e:
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
    backend = _get_backend(project_info.backend.__root__.type)
    configurator = backend.get_configurator()
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, configurator.configure_hub, project_info.backend.__root__.dict()
        )
    except HubConfigError as e:
        _error_response_on_config_error(e, path_to_config=["backend"])
    await ProjectManager.create_project_from_info(user=user, project_info=project_info)
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
    backend = _get_backend(project_info.backend.__root__.type)
    configurator = backend.get_configurator()
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, configurator.configure_hub, project_info.backend.__root__.dict()
        )
    except HubConfigError as e:
        _error_response_on_config_error(e, path_to_config=["backend"])
    await ProjectManager.update_project_from_info(project_info)
    clear_backend_cache(project_info.project_name)
    return project_info


def _get_backend(backend_type: str) -> Backend:
    backend = dict_backends(all_backend=True).get(backend_type)
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(f"Unknown backend {backend_type}"),
        )
    return backend


def _error_response_on_config_error(e: HubConfigError, path_to_config: List[str]):
    if len(e.fields) > 0:
        error_details = [
            error_detail(e.message, code=e.code, loc=path_to_config + [f]) for f in e.fields
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_details,
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=[error_detail(e.message, code=e.code)],
    )
