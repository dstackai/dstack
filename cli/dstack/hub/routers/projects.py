import asyncio
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack.api.backend import dict_backends
from dstack.backend.base import Backend
from dstack.core.error import HubConfigError
from dstack.hub.models import (
    Member,
    ProjectConfigWithCredsPartial,
    ProjectDelete,
    ProjectInfo,
    ProjectValues,
)
from dstack.hub.repository.projects import ProjectManager
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/projects", tags=["project"])


@router.post("/backends/values")
async def get_backend_config_values(
    config: ProjectConfigWithCredsPartial = Body(),
) -> ProjectValues:
    backend = _get_backend(config.__root__.type)
    configurator = backend.get_configurator()
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None, configurator.configure_hub, config.__root__.dict()
        )
    except HubConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(e.message, e.code),
        )
    return result


@router.get(
    "/list",
    dependencies=[Depends(Scope("project:list:read"))],
)
async def list_project() -> List[ProjectInfo]:
    return await ProjectManager.list_project_info()


@router.post(
    "",
    dependencies=[Depends(Scope("project:projects:write"))],
)
async def create_project(project_info: ProjectInfo) -> ProjectInfo:
    project = await ProjectManager.get(name=project_info.project_name)
    if project is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail("Project exists")
        )
    backend = _get_backend(project_info.backend.__root__.type)
    configurator = backend.get_configurator()
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, configurator.configure_hub, project_info.backend.__root__.dict()
        )
    except HubConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(e.message, e.code),
        )
    await ProjectManager.create_project_from_info(project_info)
    return project_info


@router.delete("", dependencies=[Depends(Scope("project:delete:write"))])
async def delete_project(body: ProjectDelete):
    for project_name in body.projects:
        await ProjectManager.delete(project_name)


@router.post(
    "/{project_name}/members",
    dependencies=[Depends(Scope("project:members:write"))],
)
async def set_project_members(project_name: str, body: List[Member] = Body()):
    project = await get_project(project_name=project_name)
    await ProjectManager.clear_member(project=project)
    for member in body:
        await ProjectManager.add_member(project=project, member=member)


@router.get("/{project_name}", dependencies=[Depends(Scope("project:list:read"))])
async def get_project_info(project_name: str) -> ProjectInfo:
    project = await ProjectManager.get_project_info(name=project_name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("Project not found"),
        )
    return project


@router.patch("/{project_name}", dependencies=[Depends(Scope("project:patch:write"))])
async def update_project(project_name: str, project_info: ProjectInfo = Body()) -> ProjectInfo:
    backend = _get_backend(project_info.backend.__root__.type)
    configurator = backend.get_configurator()
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, configurator.configure_hub, project_info.backend.__root__.dict()
        )
    except HubConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(e.message, e.code),
        )
    await ProjectManager.update_project_from_info(project_info)
    return project_info


def _get_backend(backend_type: str) -> Backend:
    backend = dict_backends(all_backend=True).get(backend_type)
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(f"Unknown backend {backend_type}"),
        )
    return backend
