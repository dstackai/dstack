from fastapi import APIRouter, Depends
from typing_extensions import Annotated

import dstack._internal.proxy.services.registry as registry_services
from dstack._internal.proxy.deps import get_nginx, get_proxy_repo
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.schemas.common import OkResponse
from dstack._internal.proxy.schemas.registry import (
    RegisterEntrypointRequest,
    RegisterReplicaRequest,
    RegisterServiceRequest,
)
from dstack._internal.proxy.services.nginx import Nginx

router = APIRouter(prefix="/{project}")


@router.post("/services/register")
async def register_service(
    project: str,
    body: RegisterServiceRequest,
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
) -> OkResponse:
    await registry_services.register_service(
        project_name=project.lower(),  # TODO: who should lower?
        run_name=body.run_name,
        domain=body.domain.lower(),
        https=body.https,
        auth=body.auth,
        client_max_body_size=body.client_max_body_size,
        model=None,  # TODO
        ssh_private_key=body.ssh_private_key,
        repo=repo,
        nginx=nginx,
    )
    return OkResponse()


@router.post("/services/{run_name}/unregister")
async def unregister_service(
    project: str,
    run_name: str,
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
) -> OkResponse:
    await registry_services.unregister_service(
        project_name=project.lower(),
        run_name=run_name,
        repo=repo,
        nginx=nginx,
    )
    return OkResponse()


@router.post("/services/{run_name}/replicas/register")
async def register_replica(
    project: str,
    run_name: str,
    body: RegisterReplicaRequest,
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
) -> OkResponse:
    await registry_services.register_replica(
        project_name=project.lower(),
        run_name=run_name,
        replica_id=body.job_id,
        app_port=body.app_port,
        ssh_destination=body.ssh_host,
        ssh_port=body.ssh_port,
        ssh_proxy=body.ssh_proxy,
        repo=repo,
        nginx=nginx,
    )
    return OkResponse()


@router.post("/services/{run_name}/replicas/{job_id}/unregister")
async def unregister_replica(
    project: str,
    run_name: str,
    job_id: str,
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
) -> OkResponse:
    await registry_services.unregister_replica(
        project_name=project.lower(),
        run_name=run_name,
        replica_id=job_id,
        repo=repo,
        nginx=nginx,
    )
    return OkResponse()


@router.post("/entrypoints/register")
async def register_entrypoint(
    project: str,
    body: RegisterEntrypointRequest,
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
) -> OkResponse:
    return OkResponse()
