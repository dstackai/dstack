from typing import Annotated

from fastapi import APIRouter, Depends

from dstack.gateway.errors import GatewayError
from dstack.gateway.registry.schemas import RegisterRequest, UnregisterRequest
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
