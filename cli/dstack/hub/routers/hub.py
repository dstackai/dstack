from typing import List, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from dstack.api.backend import dict_backends
from dstack.core.error import HubError
from dstack.hub.models import AWSAuth, AWSConfig, Member, ProjectDelete, ProjectInfo
from dstack.hub.repository.hub import ProjectManager
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope
from dstack.hub.util import info2project

router = APIRouter(prefix="/api/projects", tags=["project"])


security = HTTPBearer()


@router.post("/backends/values", deprecated=True)
async def backend_configurator(body: dict = Body()):
    type_backend = body.get("type")
    if type_backend is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown backend")
    backend = dict_backends(all_backend=True).get(type_backend.lower())
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{type_backend} not support"
        )
    configurator = backend.get_configurator()
    try:
        result = await configurator.configure_hub(body)
    except HubError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ex.message,
        )
    except Exception as exx:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return result


@router.get(
    "{project_name}/info",
    dependencies=[Depends(Scope("project:info:read"))],
    response_model=List[ProjectInfo],
    deprecated=True,
)
async def info_project(project_name: str) -> List[ProjectInfo]:
    project = get_project(project_name=project_name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found",
        )
    return project


@router.get(
    "/list",
    dependencies=[Depends(Scope("project:list:read"))],
    response_model=List[ProjectInfo],
    deprecated=True,
)
async def list_project() -> List[ProjectInfo]:
    return await ProjectManager.list_info()


@router.post(
    "",
    dependencies=[Depends(Scope("project:projects:write"))],
    response_model=ProjectInfo,
    deprecated=True,
)
async def project_create(body: ProjectInfo) -> ProjectInfo:
    project = await ProjectManager.get(name=body.project_name)
    if project is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project is exists")
    await ProjectManager.save(info2project(body))
    return body


@router.delete("", dependencies=[Depends(Scope("project:delete:write"))], deprecated=True)
async def delete_project(body: ProjectDelete):
    for project_name in body.projects:
        project = await get_project(project_name=project_name)
        await ProjectManager.remove(project)


@router.post(
    "/{project_name}/members",
    dependencies=[Depends(Scope("project:members:write"))],
    deprecated=True,
)
async def project_members(project_name: str, body: List[Member] = Body()):
    project = await get_project(project_name=project_name)
    await ProjectManager.clear_member(project=project)
    for member in body:
        await ProjectManager.add_member(project=project, member=member)


@router.get("/{project_name}", dependencies=[Depends(Scope("project:list:read"))], deprecated=True)
async def info_project(project_name: str) -> ProjectInfo:
    project = await ProjectManager.get_info(name=project_name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found",
        )
    return project


@router.patch(
    "/{project_name}", dependencies=[Depends(Scope("project:patch:write"))], deprecated=True
)
async def patch_project(project_name: str, payload: dict = Body()) -> ProjectInfo:
    project = await get_project(project_name=project_name)
    if payload.get("backend") is not None and payload.get("backend").get("type") == "aws":
        if payload.get("backend").get("s3_bucket_name") is not None:
            bucket = payload.get("backend").get("s3_bucket_name").replace("s3://", "")
            payload["backend"]["s3_bucket_name"] = bucket
        project.auth = AWSAuth().parse_obj(payload.get("backend")).json()
        project.config = AWSConfig().parse_obj(payload.get("backend")).json()
    await ProjectManager.save(project)
    return await ProjectManager.get_info(name=project_name)
