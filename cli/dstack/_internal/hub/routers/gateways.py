from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack._internal.core.gateway import GatewayHead
from dstack._internal.hub.routers.util import error_detail, get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.hub.utils.common import run_async
from dstack._internal.hub.utils.ssh import get_hub_ssh_public_key

router = APIRouter(
    prefix="/api/project", tags=["gateways"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/gateways/create", dependencies=[Depends(ProjectAdmin())])
async def gateways_create(project_name: str) -> GatewayHead:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    try:
        return await run_async(backend.create_gateway, get_hub_ssh_public_key())
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                msg=f"Can't create gateway for {backend.name} backend", code="not_implemented"
            ),
        )


@router.get("/{project_name}/gateways")
async def gateways_list(project_name: str) -> List[GatewayHead]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    return backend.list_gateways()


@router.post("/{project_name}/gateways/delete", dependencies=[Depends(ProjectAdmin())])
async def gateways_delete(project_name: str, instance_name: str = Body()):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await run_async(backend.delete_gateway, instance_name)
