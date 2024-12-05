import logging
from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import FastAPI

from dstack._internal.proxy.deps import BaseProxyDependencyInjector
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.repos.memory import InMemoryProxyRepo
from dstack._internal.proxy.routers.auth import router as auth_router
from dstack._internal.proxy.routers.config import router as config_router
from dstack._internal.proxy.routers.model_proxy import router as model_proxy_router
from dstack._internal.proxy.routers.registry import router as registry_router
from dstack._internal.proxy.routers.stats import router as stats_router
from dstack._internal.proxy.services.nginx import Nginx
from dstack.version import __version__


class DependencyInjector(BaseProxyDependencyInjector):
    def __init__(self) -> None:
        self._repo = InMemoryProxyRepo()
        self._nginx = Nginx()

    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        yield self._repo

    async def get_nginx(self) -> Optional[Nginx]:
        return self._nginx


def configure_logging(level: int = logging.INFO):
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger("dstack")
    logger.setLevel(level)
    logger.addHandler(handler)


configure_logging(logging.DEBUG)
app = FastAPI()
app.state.proxy_dependency_injector = DependencyInjector()

# TODO: add CORS only to openai routers once fastapi supports it.
# See https://github.com/tiangolo/fastapi/pull/11010
# app.add_middleware(
#     CORSMiddleware,
#     allow_origin_regex=".*",
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.include_router(auth_router, prefix="/auth")
app.include_router(config_router, prefix="/api/config")
app.include_router(model_proxy_router, prefix="/api/models")
app.include_router(registry_router, prefix="/api/registry")
app.include_router(stats_router, prefix="/api/stats")


@app.get("/")
def get_info():
    return {"version": __version__}
