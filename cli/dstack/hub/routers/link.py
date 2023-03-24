from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBearer

from dstack.hub.models import LinkUpload
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/project", tags=["link"])

security = HTTPBearer()


@router.post(
    "/{project_name}/link/upload",
    dependencies=[Depends(Scope("link:upload:write"))],
    response_model=str,
    response_class=PlainTextResponse,
)
async def link_upload(project_name: str, body: LinkUpload):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.get_signed_upload_url(object_key=body.object_key)


@router.get(
    "/{project_name}/link/download",
    dependencies=[Depends(Scope("link:download:read"))],
    response_model=str,
    response_class=PlainTextResponse,
)
async def link_upload(project_name: str, body: LinkUpload):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.get_signed_download_url(object_key=body.object_key)
