from fastapi import APIRouter, Depends, Request, status
from fastapi.datastructures import URL
from fastapi.responses import RedirectResponse, Response
from typing_extensions import Annotated

from dstack._internal.proxy.deps import ProxyAuth, ProxyAuthContext, get_proxy_repo
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.services import service_proxy

REDIRECTED_HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
PROXIED_HTTP_METHODS = REDIRECTED_HTTP_METHODS + ["OPTIONS"]


router = APIRouter()


@router.api_route("/{project_name}/{run_name}", methods=REDIRECTED_HTTP_METHODS)
async def redirect_to_service_root(request: Request) -> Response:
    url = URL(str(request.url))
    url = url.replace(path=url.path + "/")
    return RedirectResponse(url, status.HTTP_308_PERMANENT_REDIRECT)


@router.api_route("/{project_name}/{run_name}/{path:path}", methods=PROXIED_HTTP_METHODS)
async def service_reverse_proxy(
    project_name: str,
    run_name: str,
    path: str,
    request: Request,
    auth: Annotated[ProxyAuthContext, Depends(ProxyAuth(auto_enforce=False))],
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
) -> Response:
    return await service_proxy.proxy(project_name, run_name, path, request, auth, repo)


# TODO(#1595): support websockets
