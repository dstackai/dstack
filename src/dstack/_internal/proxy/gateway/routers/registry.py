from fastapi import APIRouter, Depends
from typing_extensions import Annotated

import dstack._internal.proxy.gateway.services.registry as registry_services
from dstack._internal.proxy.gateway.deps import get_gateway_proxy_repo, get_nginx
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.schemas.common import OkResponse
from dstack._internal.proxy.gateway.schemas.registry import (
    RegisterEntrypointRequest,
    RegisterReplicaRequest,
    RegisterServiceRequest,
)
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.lib.deps import get_service_connection_pool
from dstack._internal.proxy.lib.services.service_connection import ServiceConnectionPool

router = APIRouter(prefix="/{project_name}")


@router.post("/services/register")
async def register_service(
    project_name: str,
    body: RegisterServiceRequest,
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
    service_conn_pool: Annotated[ServiceConnectionPool, Depends(get_service_connection_pool)],
) -> OkResponse:
    await registry_services.register_service(
        project_name=project_name.lower(),
        run_name=body.run_name.lower(),
        domain=body.domain.lower(),
        https=body.https,
        rate_limits=body.rate_limits,
        auth=body.auth,
        client_max_body_size=body.client_max_body_size,
        model=body.options.openai.model if body.options.openai is not None else None,
        ssh_private_key=body.ssh_private_key,
        repo=repo,
        nginx=nginx,
        service_conn_pool=service_conn_pool,
    )
    return OkResponse()


@router.post("/services/{run_name}/unregister")
async def unregister_service(
    project_name: str,
    run_name: str,
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
    service_conn_pool: Annotated[ServiceConnectionPool, Depends(get_service_connection_pool)],
) -> OkResponse:
    await registry_services.unregister_service(
        project_name=project_name.lower(),
        run_name=run_name.lower(),
        repo=repo,
        nginx=nginx,
        service_conn_pool=service_conn_pool,
    )
    return OkResponse()


@router.post("/services/{run_name}/replicas/register")
async def register_replica(
    project_name: str,
    run_name: str,
    body: RegisterReplicaRequest,
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
    service_conn_pool: Annotated[ServiceConnectionPool, Depends(get_service_connection_pool)],
) -> OkResponse:
    await registry_services.register_replica(
        project_name=project_name.lower(),
        run_name=run_name.lower(),
        replica_id=body.job_id,
        app_port=body.app_port,
        ssh_destination=body.ssh_host,
        ssh_port=body.ssh_port,
        ssh_proxy=body.ssh_proxy,
        ssh_head_proxy=body.ssh_head_proxy,
        ssh_head_proxy_private_key=body.ssh_head_proxy_private_key,
        repo=repo,
        nginx=nginx,
        service_conn_pool=service_conn_pool,
    )
    return OkResponse()


@router.post("/services/{run_name}/replicas/{job_id}/unregister")
async def unregister_replica(
    project_name: str,
    run_name: str,
    job_id: str,
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
    service_conn_pool: Annotated[ServiceConnectionPool, Depends(get_service_connection_pool)],
) -> OkResponse:
    await registry_services.unregister_replica(
        project_name=project_name.lower(),
        run_name=run_name.lower(),
        replica_id=job_id,
        repo=repo,
        nginx=nginx,
        service_conn_pool=service_conn_pool,
    )
    return OkResponse()


@router.post("/entrypoints/register")
async def register_entrypoint(
    project_name: str,
    body: RegisterEntrypointRequest,
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
) -> OkResponse:
    await registry_services.register_model_entrypoint(
        project_name=project_name.lower(),
        domain=body.domain.lower(),
        https=body.https,
        repo=repo,
        nginx=nginx,
    )
    return OkResponse()
