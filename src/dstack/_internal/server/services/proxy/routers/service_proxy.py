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


@router.get("/{project_name}/{run_name}")
@router.post("/{project_name}/{run_name}")
@router.put("/{project_name}/{run_name}")
@router.delete("/{project_name}/{run_name}")
@router.patch("/{project_name}/{run_name}")
@router.head("/{project_name}/{run_name}")
async def redirect_to_service_root(request: Request, project_name: str, run_name: str) -> Response:
    url = URL(str(request.url))
    url = url.replace(path=url.path + "/")
    return RedirectResponse(url, status.HTTP_308_PERMANENT_REDIRECT)


@router.get("/{project_name}/{run_name}/{path:path}")
@router.post("/{project_name}/{run_name}/{path:path}")
@router.put("/{project_name}/{run_name}/{path:path}")
@router.delete("/{project_name}/{run_name}/{path:path}")
@router.patch("/{project_name}/{run_name}/{path:path}")
@router.head("/{project_name}/{run_name}/{path:path}")
@router.options("/{project_name}/{run_name}/{path:path}")
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
