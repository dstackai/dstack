from typing import AsyncGenerator, Optional, Tuple

import httpx
from fastapi import FastAPI

from dstack._internal.proxy.deps import BaseProxyDependencyInjector
from dstack._internal.proxy.repos.base import BaseProxyRepo, Project, Replica, Service
from dstack._internal.proxy.routers.model_proxy import router as model_router
from dstack._internal.proxy.routers.service_proxy import router as service_router


def make_app(repo: BaseProxyRepo) -> FastAPI:
    class DependencyInjector(BaseProxyDependencyInjector):
        async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
            yield repo

    app = FastAPI()
    app.state.proxy_dependency_injector = DependencyInjector()
    app.include_router(service_router, prefix="/proxy/services")
    app.include_router(model_router, prefix="/proxy/models")
    return app


def make_client(app: FastAPI, auth_token: Optional[str] = None) -> httpx.AsyncClient:
    headers = None
    if auth_token is not None:
        headers = {"Authorization": f"Bearer {auth_token}"}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), headers=headers)


def make_app_client(
    repo: BaseProxyRepo, auth_token: Optional[str] = None
) -> Tuple[FastAPI, httpx.AsyncClient]:
    app = make_app(repo)
    client = make_client(app, auth_token)
    return app, client


def make_project(name: str) -> Project:
    return Project(name=name, ssh_private_key="secret")


def make_service(run_name: str, auth: bool = False) -> Service:
    return Service(
        id="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        run_name=run_name,
        auth=auth,
        app_port=80,
        replicas=[
            Replica(
                id="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                ssh_destination="ubuntu@server",
                ssh_port=22,
                ssh_proxy=None,
            )
        ],
    )
