"""FastAPI app running on a gateway."""

import asyncio
import contextlib
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dstack._internal.proxy.gateway.auth import GatewayProxyAuthProvider
from dstack._internal.proxy.gateway.const import (
    DSTACK_DIR_ON_GATEWAY,
    SERVER_CONNECTIONS_DIR_ON_GATEWAY,
)
from dstack._internal.proxy.gateway.deps import (
    GatewayDependencyInjector,
    get_gateway_injector_from_app,
    get_gateway_proxy_repo,
)
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.repo.state_v1 import migrate_from_state_v1
from dstack._internal.proxy.gateway.routers.auth import router as auth_router
from dstack._internal.proxy.gateway.routers.config import router as config_router
from dstack._internal.proxy.gateway.routers.registry import router as registry_router
from dstack._internal.proxy.gateway.routers.services import router as services_router
from dstack._internal.proxy.gateway.routers.stats import router as stats_router
from dstack._internal.proxy.gateway.routers.usage import router as usage_router
from dstack._internal.proxy.gateway.services.metering import Clock, MeteringCollector
from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.services.registry import ACCESS_LOG_PATH, apply_all
from dstack._internal.proxy.gateway.services.server_client import HTTPMultiClient
from dstack._internal.proxy.gateway.services.stats import StatsCollector
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.routers.model_proxy import router as model_proxy_router
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger
from dstack.version import __version__

STATE_FILE = DSTACK_DIR_ON_GATEWAY / "state-v2.json"
LEGACY_STATE_FILE = DSTACK_DIR_ON_GATEWAY / "state.json"
LEGACY_KEYS_DIR = Path("~/.ssh/projects").expanduser().resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    injector = get_gateway_injector_from_app(app)
    repo = await get_gateway_proxy_repo(await injector.get_repo().__anext__())
    nginx = injector.get_nginx()
    service_conn_pool = await injector.get_service_connection_pool()
    await run_async(nginx.write_global_conf)
    await apply_all(repo, nginx, service_conn_pool)

    metering = injector.get_metering()
    await metering.configure_profiles((await repo.get_config()).usage_metering_profiles)
    maintenance = asyncio.create_task(_metering_maintenance(metering))
    try:
        yield
    finally:
        maintenance.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance
        try:
            await metering.close()
        finally:
            await service_conn_pool.remove_all()


def make_app(
    repo: Optional[GatewayProxyRepo] = None,
    nginx: Optional[Nginx] = None,
    metering_store: MeteringStore | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    if repo is None:
        migrate_from_state_v1(
            v1_file=LEGACY_STATE_FILE, v2_file=STATE_FILE, keys_dir=LEGACY_KEYS_DIR
        )
        repo = GatewayProxyRepo.load(STATE_FILE)

    app = FastAPI(lifespan=lifespan)
    app.state.proxy_dependency_injector = GatewayDependencyInjector(
        repo=repo,
        auth=GatewayProxyAuthProvider(
            server_client=HTTPMultiClient(SERVER_CONNECTIONS_DIR_ON_GATEWAY)
        ),
        nginx=nginx or Nginx(),
        stats_collector=StatsCollector(ACCESS_LOG_PATH),
        metering=MeteringCollector(
            metering_store or MeteringStore(DSTACK_DIR_ON_GATEWAY / "usage-counters.json"),
            clock=clock,
        ),
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
    app.include_router(services_router, prefix="/api/services")
    app.include_router(stats_router, prefix="/api/stats")
    app.include_router(usage_router, prefix="/api/usage")

    @app.get("/")
    def get_info():
        return {"version": __version__}

    return app


async def _metering_maintenance(metering: MeteringCollector) -> None:
    last_checkpoint = time.monotonic()
    while True:
        await asyncio.sleep(1)
        try:
            await metering.rotate_if_due()
            if time.monotonic() - last_checkpoint >= 60:
                await metering.checkpoint()
                last_checkpoint = time.monotonic()
        except (OSError, ValueError, ProxyError):
            get_logger(__name__).exception("Usage maintenance failed; metered admission paused")
