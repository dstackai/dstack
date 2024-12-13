"""FastAPI app running on a gateway."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dstack._internal.proxy.gateway.auth import GatewayProxyAuthProvider
from dstack._internal.proxy.gateway.const import SERVER_CONNECTIONS_DIR_ON_GATEWAY
from dstack._internal.proxy.gateway.deps import (
    GatewayDependencyInjector,
    get_gateway_injector_from_app,
)
from dstack._internal.proxy.gateway.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.routers.auth import router as auth_router
from dstack._internal.proxy.gateway.routers.config import router as config_router
from dstack._internal.proxy.gateway.routers.registry import router as registry_router
from dstack._internal.proxy.gateway.routers.stats import router as stats_router
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.services.registry import ACCESS_LOG_PATH
from dstack._internal.proxy.gateway.services.server_client import HTTPMultiClient
from dstack._internal.proxy.gateway.services.stats import StatsCollector
from dstack._internal.proxy.lib.routers.model_proxy import router as model_proxy_router
from dstack._internal.proxy.lib.services.service_connection import service_replica_connection_pool
from dstack._internal.utils.common import run_async
from dstack.version import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    injector = get_gateway_injector_from_app(app)
    nginx = injector.get_nginx()
    await run_async(nginx.write_global_conf)

    yield

    await service_replica_connection_pool.remove_all()


def make_app(repo: Optional[GatewayProxyRepo] = None, nginx: Optional[Nginx] = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.proxy_dependency_injector = GatewayDependencyInjector(
        repo=repo or GatewayProxyRepo(),
        auth=GatewayProxyAuthProvider(
            server_client=HTTPMultiClient(SERVER_CONNECTIONS_DIR_ON_GATEWAY)
        ),
        nginx=nginx or Nginx(),
        stats_collector=StatsCollector(ACCESS_LOG_PATH),
    )

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
