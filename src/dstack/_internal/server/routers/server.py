from fastapi import APIRouter

from dstack._internal import settings
from dstack._internal.core.models.server import ServerInfo
from dstack._internal.server.utils.routers import CustomORJSONResponse

router = APIRouter(
    prefix="/api/server",
    tags=["server"],
)


@router.post("/get_info", response_model=ServerInfo)
async def get_server_info():
    return CustomORJSONResponse(
        ServerInfo(
            server_version=settings.DSTACK_VERSION,
        )
    )
