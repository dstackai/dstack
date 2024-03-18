from typing import Annotated

from fastapi import APIRouter, Depends

from dstack.gateway.common import OkResponse
from dstack.gateway.config.schemas import ConfigRequest
from dstack.gateway.core.store import Store, get_store

router = APIRouter()


@router.post("")
async def post_config(
    body: ConfigRequest,
    store: Annotated[Store, Depends(get_store)],
) -> OkResponse:
    await store.update_config(body.acme_server, body.acme_eab_kid, body.acme_eab_hmac_key)
    return OkResponse()
