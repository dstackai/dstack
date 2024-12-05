from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dstack._internal.proxy.deps import BaseProxyDependencyInjector
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.repos.gateway import GatewayProxyRepo
from dstack._internal.proxy.routers.auth import router as auth_router
from dstack._internal.proxy.routers.config import router as config_router
from dstack._internal.proxy.routers.model_proxy import router as model_proxy_router
from dstack._internal.proxy.routers.registry import router as registry_router
from dstack._internal.proxy.routers.stats import router as stats_router
from dstack._internal.proxy.services.auth.base import BaseProxyAuthProvider
from dstack._internal.proxy.services.auth.gateway import GatewayProxyAuthProvider
from dstack._internal.proxy.services.nginx import Nginx
from dstack._internal.proxy.services.registry import ACCESS_LOG_PATH
from dstack._internal.proxy.services.server_client import HTTPMultiClient
from dstack._internal.proxy.services.stats import StatsCollector
from dstack.version import __version__


class DependencyInjector(BaseProxyDependencyInjector):
    def __init__(self, repo: GatewayProxyRepo) -> None:
        self._repo = repo
        self._auth_provider = GatewayProxyAuthProvider(
            # TODO: const
            server_client=HTTPMultiClient(Path("/home/ubuntu/dstack/server-connections/"))
        )
        self._nginx = Nginx()
        self._stats_collector = StatsCollector(ACCESS_LOG_PATH)

    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        yield self._repo

    async def get_auth_provider(self) -> AsyncGenerator[BaseProxyAuthProvider, None]:
        yield self._auth_provider

    async def get_nginx(self) -> Optional[Nginx]:
        return self._nginx

    async def get_stats_collector(self):
        return self._stats_collector


def make_app(repo: Optional[GatewayProxyRepo] = None) -> FastAPI:
    app = FastAPI()
    app.state.proxy_dependency_injector = DependencyInjector(repo or GatewayProxyRepo())

    # TODO: add CORS only to openai routers once fastapi supports it.
    # See https://github.com/tiangolo/fastapi/pull/11010
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(config_router, prefix="/api/config")
    app.include_router(model_proxy_router, prefix="/api/models")
    app.include_router(registry_router, prefix="/api/registry")
    app.include_router(stats_router, prefix="/api/stats")

    @app.get("/")
    def get_info():
        return {"version": __version__}

    return app
