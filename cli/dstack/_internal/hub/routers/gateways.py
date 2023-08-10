from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack._internal.core.gateway import GatewayHead
from dstack._internal.hub.routers.util import call_backend, error_detail, get_backends, get_project
from dstack._internal.hub.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.hub.utils.common import run_async
from dstack._internal.hub.utils.ssh import get_hub_ssh_public_key

router = APIRouter(
    prefix="/api/project", tags=["gateways"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/gateways/create", dependencies=[Depends(ProjectAdmin())])
async def gateways_create(project_name: str) -> GatewayHead:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        try:
            return await call_backend(backend.create_gateway, get_hub_ssh_public_key())
        except NotImplementedError:
            pass
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail(
            msg=f"Can't create gateway for {project_name} project. No backend supporting gateway",
            code="not_implemented",
        ),
    )


@router.get("/{project_name}/gateways")
async def gateways_list(project_name: str) -> List[GatewayHead]:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    gateways = []
    for _, backend in backends:
        gateways += await call_backend(backend.list_gateways)
    return gateways


@router.post("/{project_name}/gateways/delete", dependencies=[Depends(ProjectAdmin())])
async def gateways_delete(project_name: str, instance_name: str = Body()):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        await call_backend(backend.delete_gateway, instance_name)
