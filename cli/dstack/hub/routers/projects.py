import asyncio
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack.api.backend import dict_backends
from dstack.core.error import HubError
from dstack.hub.models import (
    AWSProjectConfig,
    AWSProjectCreds,
    Member,
    ProjectConfigWithCreds,
    ProjectDelete,
    ProjectInfo,
    ProjectValues,
)
from dstack.hub.repository.hub import ProjectManager
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope
from dstack.hub.util import info2project

router = APIRouter(prefix="/api/projects", tags=["project"])


@router.post("/backends/values")
async def backend_configurator(config: ProjectConfigWithCreds = Body()) -> ProjectValues:
    data = config.__root__.dict()
    backend = dict_backends(all_backend=True).get(data.get("type").lower())
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown backend {data.get('type')}"
        )
    configurator = backend.get_configurator()
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None, configurator.configure_hub, data
        )
    except HubError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ex.message,
        )
    return result


@router.get(
    "/list",
    dependencies=[Depends(Scope("project:list:read"))],
)
async def list_project() -> List[ProjectInfo]:
    return await ProjectManager.list_info()


@router.post(
    "",
    dependencies=[Depends(Scope("project:projects:write"))],
)
async def create_project(body: ProjectInfo) -> ProjectInfo:
    # TODO validate config
    project = await ProjectManager.get(name=body.project_name)
    if project is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project exists")
    await ProjectManager.save(info2project(body))
    return body


@router.delete("", dependencies=[Depends(Scope("project:delete:write"))])
async def delete_project(body: ProjectDelete):
    for project_name in body.projects:
        project = await get_project(project_name=project_name)
        await ProjectManager.remove(project)


@router.post(
    "/{project_name}/members",
    dependencies=[Depends(Scope("project:members:write"))],
)
async def project_members(project_name: str, body: List[Member] = Body()):
    project = await get_project(project_name=project_name)
    await ProjectManager.clear_member(project=project)
    for member in body:
        await ProjectManager.add_member(project=project, member=member)


@router.get("/{project_name}", dependencies=[Depends(Scope("project:list:read"))])
async def info_project(project_name: str) -> ProjectInfo:
    project = await ProjectManager.get_info(name=project_name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found",
        )
    return project


@router.patch("/{project_name}", dependencies=[Depends(Scope("project:patch:write"))])
async def patch_project(project_name: str, payload: dict = Body()) -> ProjectInfo:
    project = await get_project(project_name=project_name)
    if payload.get("backend") is not None and payload.get("backend").get("type") == "aws":
        if payload.get("backend").get("s3_bucket_name") is not None:
            bucket = payload.get("backend").get("s3_bucket_name").replace("s3://", "")
            payload["backend"]["s3_bucket_name"] = bucket
        project.auth = AWSProjectCreds.parse_obj(payload.get("backend")).json()
        project.config = AWSProjectConfig.parse_obj(payload.get("backend")).json()
    await ProjectManager.save(project)
    return await ProjectManager.get_info(name=project_name)
