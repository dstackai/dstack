from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBearer

from dstack.hub.models import LinkUpload
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["link"])

security = HTTPBearer()


@router.post(
    "/{hub_name}/link/upload",
    dependencies=[Depends(Scope("link:upload:write"))],
    response_model=str,
    response_class=PlainTextResponse,
)
async def link_upload(hub_name: str, body: LinkUpload):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    return backend.get_signed_upload_url(object_key=body.object_key)


@router.get(
    "/{hub_name}/link/download",
    dependencies=[Depends(Scope("link:download:read"))],
    response_model=str,
    response_class=PlainTextResponse,
)
async def link_upload(hub_name: str, body: LinkUpload):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    return backend.get_signed_download_url(object_key=body.object_key)
