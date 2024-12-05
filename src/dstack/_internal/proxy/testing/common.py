from typing import AsyncGenerator, Optional, Tuple

import httpx
from fastapi import FastAPI

from dstack._internal.proxy.deps import BaseProxyDependencyInjector
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.repos.gateway import GatewayProxyRepo
from dstack._internal.proxy.repos.models import Project, Replica, Service
from dstack._internal.proxy.routers.model_proxy import router as model_router
from dstack._internal.proxy.routers.service_proxy import router as service_router
from dstack._internal.proxy.services.auth.base import BaseProxyAuthProvider
from dstack._internal.proxy.testing.auth import ProxyTestAuthProvider


def make_app(
    repo: BaseProxyRepo = GatewayProxyRepo(), auth: BaseProxyAuthProvider = ProxyTestAuthProvider()
) -> FastAPI:
    """
    Creates an app with routes similar to in-server proxy but allows overriding dependencies.
    It makes sense to use GatewayProxyRepo (even though it's meant for gateways) and
    ProxyTestAuthProvider in unit tests, since they are easier to populate than ServerProxyRepo
    and ServerProxyAuthProvider.
    """

    class DependencyInjector(BaseProxyDependencyInjector):
        async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
            yield repo

        async def get_auth_provider(self) -> AsyncGenerator[BaseProxyAuthProvider, None]:
            yield auth

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
    repo: BaseProxyRepo = GatewayProxyRepo(),
    auth: BaseProxyAuthProvider = ProxyTestAuthProvider(),
    auth_token: Optional[str] = None,
) -> Tuple[FastAPI, httpx.AsyncClient]:
    app = make_app(repo, auth)
    client = make_client(app, auth_token)
    return app, client


def make_project(name: str) -> Project:
    return Project(name=name, ssh_private_key="secret")


def make_service(
    project_name: str, run_name: str, domain: Optional[str] = None, auth: bool = False
) -> Service:
    return Service(
        project_name=project_name,
        run_name=run_name,
        domain=domain,
        https=None,
        auth=auth,
        client_max_body_size=2**20,
        replicas=frozenset(
            [
                Replica(
                    id="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                    app_port=80,
                    ssh_destination="ubuntu@server",
                    ssh_port=22,
                    ssh_proxy=None,
                )
            ]
        ),
    )
