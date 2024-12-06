from fastapi import APIRouter

from dstack._internal import settings
from dstack._internal.core.models.server import ServerInfo

router = APIRouter(
    prefix="/api/server",
    tags=["server"],
)


@router.post("/get_info")
async def get_server_info() -> ServerInfo:
    return ServerInfo(
        server_version=settings.DSTACK_VERSION,
    )
