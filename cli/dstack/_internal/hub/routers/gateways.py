from collections import defaultdict
from typing import List

import dns.exception
import dns.resolver
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel

from dstack._internal.core.gateway import Gateway, GatewayBackend
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.routers.util import call_backend, error_detail, get_project
from dstack._internal.hub.schemas import AWSBackendConfig, AzureBackendConfig, GCPBackendConfig
from dstack._internal.hub.schemas.gateways import (
    GatewayCreate,
    GatewayDelete,
    GatewayTestDomain,
    GatewayUpdate,
)
from dstack._internal.hub.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.hub.services.backends import get_configurator
from dstack._internal.hub.services.common import get_backends
from dstack._internal.hub.utils.gateway import get_gateway, list_gateways
from dstack._internal.utils.random_names import generate_name

router = APIRouter(
    prefix="/api/project", tags=["gateways"], dependencies=[Depends(ProjectMember())]
)
supported_backends = ["aws", "azure", "gcp"]


class Message(BaseModel):
    msg: str


@router.get("/{project_name}/gateways/list_backends")
async def gateways_list_backends(project_name: str) -> List[GatewayBackend]:
    project = await get_project(project_name=project_name)
    return await _get_gateway_backends(project)


@router.post(
    "/{project_name}/gateways/create",
    dependencies=[Depends(ProjectAdmin())],
    responses={400: {"model": Message}},
)
async def gateway_create(project_name: str, body: GatewayCreate = Body()) -> Gateway:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)

    gateway_names = {gateway.head.instance_name for gateway in await list_gateways(project)}
    while True:
        instance_name = f"dstack-gateway-{generate_name()}"
        if instance_name not in gateway_names:
            break

    if body.backend in supported_backends:
        for _, backend in backends:
            if backend.name != body.backend:
                continue
            head = await call_backend(
                backend.create_gateway, instance_name, project.ssh_public_key, body.region
            )
            default = False
            if not gateway_names:  # first gateway becomes default
                default = True
                await ProjectManager.set_default_gateway(project_name, instance_name)
            return Gateway(backend=backend.name, head=head, default=default)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail(
            msg=f"Can't create gateway for {project_name} project. No {body.backend} backend supporting gateway",
            code="not_implemented",
        ),
    )


@router.get("/{project_name}/gateways")
async def gateways_list(project_name: str) -> List[Gateway]:
    project = await get_project(project_name=project_name)
    return await list_gateways(project)


@router.post("/{project_name}/gateways/delete", dependencies=[Depends(ProjectAdmin())])
async def gateway_delete(project_name: str, body: GatewayDelete = Body()):
    project = await get_project(project_name=project_name)
    backend_gateways = defaultdict(list)
    for gateway in await list_gateways(project):
        backend_gateways[gateway.backend].append((gateway.head.instance_name, gateway.head.region))

    backends = await get_backends(project, selected_backends=list(backend_gateways.keys()))
    for _, backend in backends:
        for instance_name, region in backend_gateways[backend.name]:
            if instance_name in body.instance_names:
                await call_backend(backend.delete_gateway, instance_name, region)


@router.get("/{project_name}/gateways/{instance_name}")
async def gateway_get(project_name: str, instance_name: str) -> Gateway:
    project = await get_project(project_name=project_name)
    gateway = await get_gateway(project, instance_name)
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return gateway


@router.post(
    "/{project_name}/gateways/{instance_name}/update", dependencies=[Depends(ProjectAdmin())]
)
async def gateway_update(project_name: str, instance_name: str, body: GatewayUpdate = Body()):
    project = await get_project(project_name=project_name)
    gateway = await get_gateway(project, instance_name)
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    backend = (await get_backends(project, selected_backends=[gateway.backend]))[0][1]

    if body.default:
        await ProjectManager.set_default_gateway(project_name, instance_name)
    elif body.default is False and project.default_gateway == instance_name:
        await ProjectManager.set_default_gateway(project_name, None)

    if body.wildcard_domain is not None:
        await call_backend(backend.update_gateway, instance_name, body.wildcard_domain)


@router.post(
    "/{project_name}/gateways/{instance_name}/test_domain",
    dependencies=[Depends(ProjectAdmin())],
    responses={400: {"model": Message}},
)
async def gateway_test_domain(
    project_name: str, instance_name: str, body: GatewayTestDomain = Body()
):
    project = await get_project(project_name)
    gateway = await get_gateway(project, instance_name)
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    try:
        for rdata in dns.resolver.resolve(body.domain, "A"):
            if rdata.address == gateway.head.external_ip:
                return
    except dns.exception.DNSException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                msg="DNS error occurred during the test",
            ),
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail(
            msg="Wildcard record is not pointing to the gateway",
        ),
    )


async def _get_gateway_backends(project: Project) -> List[GatewayBackend]:
    gateway_backends = []
    backends = await get_backends(project)
    for db_backend, backend in backends:
        if backend.name not in supported_backends:
            continue
        configurator = get_configurator(backend.name)
        regions = []
        if configurator is not None:
            config = configurator.get_backend_config(db_backend, include_creds=False)
            if isinstance(config, (AWSBackendConfig, GCPBackendConfig)):
                regions = config.regions
            elif isinstance(config, AzureBackendConfig):
                regions = config.locations
        gateway_backends.append(GatewayBackend(backend=backend.name, regions=regions))
    return gateway_backends
