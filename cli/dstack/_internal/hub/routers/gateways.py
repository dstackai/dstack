import asyncio
from typing import Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, status

from dstack._internal.core.gateway import GatewayHead
from dstack._internal.hub.routers.util import call_backend, error_detail, get_backends, get_project
from dstack._internal.hub.schemas import GatewayDelete
from dstack._internal.hub.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.hub.utils.ssh import get_hub_ssh_public_key

router = APIRouter(
    prefix="/api/project", tags=["gateways"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/gateways/create", dependencies=[Depends(ProjectAdmin())])
async def gateways_create(project_name: str, backend_name: str = Body()) -> GatewayHead:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        if backend.name != backend_name:
            continue
        try:
            return await call_backend(backend.create_gateway, project.ssh_public_key)
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
async def gateways_list(project_name: str) -> Dict[str, List[GatewayHead]]:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    tasks = [call_backend(backend.list_gateways) for _, backend in backends]
    return {
        backend.name: gateways
        for (_, backend), gateways in zip(backends, await asyncio.gather(*tasks))
    }


@router.post("/{project_name}/gateways/delete", dependencies=[Depends(ProjectAdmin())])
async def gateways_delete(project_name: str, body: GatewayDelete = Body()):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        if backend.name == body.backend:
            await call_backend(backend.delete_gateway, body.instance_name)
