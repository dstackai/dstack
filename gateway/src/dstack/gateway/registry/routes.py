from typing import Annotated

from fastapi import APIRouter, Depends

from dstack.gateway.core.store import Replica, Service, Store, get_store
from dstack.gateway.registry.schemas import (
    OkResponse,
    RegisterEntrypointRequest,
    RegisterReplicaRequest,
    RegisterServiceRequest,
)

router = APIRouter(prefix="/{project}")


@router.post("/services/register")
async def post_register_service(
    project: str, body: RegisterServiceRequest, store: Annotated[Store, Depends(get_store)]
) -> OkResponse:
    await store.register_service(
        project,
        Service(
            id=body.run_id,
            domain=body.domain.lower(),
            auth=body.auth,
            options=body.options,
        ),
        body.ssh_private_key,
    )
    return OkResponse()


@router.post("/services/{run_id}/unregister")
async def post_unregister_services(
    project: str, run_id: str, store: Annotated[Store, Depends(get_store)]
) -> OkResponse:
    await store.unregister_service(project, run_id)
    return OkResponse()


@router.post("/services/{run_id}/replicas/register")
async def post_register_replica(
    project: str,
    run_id: str,
    body: RegisterReplicaRequest,
    store: Annotated[Store, Depends(get_store)],
) -> OkResponse:
    await store.register_replica(
        project,
        run_id,
        Replica(
            id=body.job_id,
            app_port=body.app_port,
            ssh_host=body.ssh_host,
            ssh_port=body.ssh_port,
            ssh_jump_host=body.ssh_jump_host,
            ssh_jump_port=body.ssh_jump_port,
        ),
    )
    return OkResponse()


@router.post("/services/{run_id}/replicas/{job_id}/unregister")
async def post_unregister_replica(
    project: str, run_id: str, job_id: str, store: Annotated[Store, Depends(get_store)]
) -> OkResponse:
    await store.unregister_replica(project, run_id, job_id)
    return OkResponse()


@router.post("/entrypoints/register")
async def post_register_entrypoint(
    project: str,
    body: RegisterEntrypointRequest,
    store: Annotated[Store, Depends(get_store)],
) -> OkResponse:
    await store.register_entrypoint(project, body.domain.lower(), body.module)
    return OkResponse()
