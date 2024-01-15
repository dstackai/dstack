from typing import Annotated

from fastapi import APIRouter, Depends

from dstack.gateway.errors import GatewayError
from dstack.gateway.registry.schemas import (
    PreflightRequest,
    RegisterEntrypointRequest,
    RegisterRequest,
    UnregisterRequest,
)
from dstack.gateway.services.store import Store, get_store

router = APIRouter()


@router.post("/{project}/register")
async def post_register(
    project: str, body: RegisterRequest, store: Annotated[Store, Depends(get_store)]
):
    try:
        await store.register(project, body)
    except GatewayError as e:
        raise e.http()
    return "ok"


@router.post("/{project}/unregister")
async def post_unregister(
    project: str, body: UnregisterRequest, store: Annotated[Store, Depends(get_store)]
):
    try:
        await store.unregister(project, body.public_domain)
    except GatewayError as e:
        raise e.http()
    return "ok"


@router.post("/{project}/{module}/register")
async def post_register_entrypoint(
    project: str,
    module: str,
    body: RegisterEntrypointRequest,
    store: Annotated[Store, Depends(get_store)],
):
    try:
        await store.register_entrypoint(project, body.domain, module)
    except GatewayError as e:
        raise e.http()
    return "ok"


@router.post("/{project}/preflight")
async def post_preflight(
    project: str, body: PreflightRequest, store: Annotated[Store, Depends(get_store)]
):
    try:
        await store.preflight(project, body.public_domain, body.ssh_private_key)
    except GatewayError as e:
        raise e.http()
    return "ok"
