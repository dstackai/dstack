from fastapi import APIRouter, Depends, Request, status
from fastapi.datastructures import URL
from fastapi.responses import RedirectResponse, Response
from typing_extensions import Annotated

from dstack._internal.proxy.lib.deps import (
    ProxyAuth,
    ProxyAuthContext,
    get_proxy_repo,
    get_service_connection_pool,
)
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.proxy.lib.services.service_connection import ServiceConnectionPool
from dstack._internal.server.services.proxy.services import service_proxy

router = APIRouter()


@router.get("/{project_name}/{run_name}", summary="Redirect to service root")
@router.post("/{project_name}/{run_name}", summary="Redirect to service root")
@router.put("/{project_name}/{run_name}", summary="Redirect to service root")
@router.delete("/{project_name}/{run_name}", summary="Redirect to service root")
@router.patch("/{project_name}/{run_name}", summary="Redirect to service root")
@router.head("/{project_name}/{run_name}", summary="Redirect to service root")
async def redirect_to_service_root(request: Request, project_name: str, run_name: str) -> Response:
    url = URL(str(request.url))
    url = url.replace(path=url.path + "/")
    return RedirectResponse(url, status.HTTP_308_PERMANENT_REDIRECT)


@router.get("/{project_name}/{run_name}/{path:path}", summary="Proxy service request")
@router.post("/{project_name}/{run_name}/{path:path}", summary="Proxy service request")
@router.put("/{project_name}/{run_name}/{path:path}", summary="Proxy service request")
@router.delete("/{project_name}/{run_name}/{path:path}", summary="Proxy service request")
@router.patch("/{project_name}/{run_name}/{path:path}", summary="Proxy service request")
@router.head("/{project_name}/{run_name}/{path:path}", summary="Proxy service request")
@router.options("/{project_name}/{run_name}/{path:path}", summary="Proxy service request")
async def service_reverse_proxy(
    project_name: str,
    run_name: str,
    path: str,
    request: Request,
    auth: Annotated[ProxyAuthContext, Depends(ProxyAuth(auto_enforce=False))],
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    service_conn_pool: Annotated[ServiceConnectionPool, Depends(get_service_connection_pool)],
) -> Response:
    return await service_proxy.proxy(
        project_name, run_name, path, request, auth, repo, service_conn_pool
    )
