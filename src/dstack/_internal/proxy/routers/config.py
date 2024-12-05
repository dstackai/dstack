from fastapi import APIRouter

from dstack._internal.proxy.schemas.common import OkResponse
from dstack._internal.proxy.schemas.config import ConfigRequest

router = APIRouter()


@router.post("")
async def post_config(body: ConfigRequest) -> OkResponse:
    # TODO
    return OkResponse()
