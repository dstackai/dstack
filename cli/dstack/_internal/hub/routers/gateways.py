from typing import List

from fastapi import APIRouter, Depends

from dstack._internal.core.gateway import GatewayHead
from dstack._internal.hub.routers.util import get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.hub.utils.ssh import get_hub_ssh_public_key

router = APIRouter(
    prefix="/api/project", tags=["gateways"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/gateways/create", dependencies=[Depends(ProjectAdmin())])
async def gateways_create(project_name: str) -> GatewayHead:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    return backend.create_gateway(ssh_key_pub=get_hub_ssh_public_key())


@router.get("/{project_name}/gateways")
async def gateways_list(project_name: str) -> List[GatewayHead]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    return backend.list_gateways()
