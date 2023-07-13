from fastapi import APIRouter, Depends, Request, Security
from fastapi.responses import PlainTextResponse
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from dstack._internal.backend.local import LocalBackend
from dstack._internal.hub.models import StorageLink
from dstack._internal.hub.routers.util import get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.utils.common import run_async

router = APIRouter(prefix="/api/project", tags=["link"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/link/upload",
    response_model=str,
    response_class=PlainTextResponse,
)
async def link_upload(
    project_name: str,
    body: StorageLink,
    request: Request,
    token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    if isinstance(backend, LocalBackend):
        return str(
            request.url_for("put_file", project_name=project_name).replace_query_params(
                key=body.object_key,
                token=token.credentials,
            )
        )
    url = await run_async(backend.get_signed_upload_url, body.object_key)
    return url


@router.post(
    "/{project_name}/link/download",
    response_model=str,
    response_class=PlainTextResponse,
)
async def link_download(
    project_name: str,
    body: StorageLink,
    request: Request,
    token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    if isinstance(backend, LocalBackend):
        print(request.url_for("download_file", project_name=project_name))
        return str(
            request.url_for("download_file", project_name=project_name).replace_query_params(
                key=body.object_key,
                token=token.credentials,
            )
        )
    url = await run_async(backend.get_signed_download_url, body.object_key)
    return url
