from typing import Annotated, AsyncGenerator

from fastapi import Depends, FastAPI, Request

from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.services.stats import StatsCollector
from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.deps import (
    ProxyDependencyInjector,
    get_injector_from_app,
    get_proxy_repo,
)
from dstack._internal.proxy.lib.errors import UnexpectedProxyError
from dstack._internal.proxy.lib.repo import BaseProxyRepo


class GatewayDependencyInjector(ProxyDependencyInjector):
    def __init__(
        self,
        repo: GatewayProxyRepo,
        auth: BaseProxyAuthProvider,
        nginx: Nginx,
        stats_collector: StatsCollector,
    ) -> None:
        super().__init__()
        self._repo = repo
        self._auth = auth
        self._nginx = nginx
        self._stats_collector = stats_collector

    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        yield self._repo

    async def get_auth_provider(self) -> AsyncGenerator[BaseProxyAuthProvider, None]:
        yield self._auth

    def get_nginx(self) -> Nginx:
        return self._nginx

    def get_stats_collector(self) -> StatsCollector:
        return self._stats_collector


def get_gateway_injector_from_app(app: FastAPI) -> GatewayDependencyInjector:
    injector = get_injector_from_app(app)
    if not isinstance(injector, GatewayDependencyInjector):
        raise UnexpectedProxyError(f"Unexpected gateway injector type: {type(injector)}")
    return injector


async def get_gateway_injector(request: Request) -> GatewayDependencyInjector:
    return get_gateway_injector_from_app(request.app)


async def get_gateway_proxy_repo(
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
) -> GatewayProxyRepo:
    if not isinstance(repo, GatewayProxyRepo):
        raise UnexpectedProxyError(f"Unexpected gateway repo type: {type(repo)}")
    return repo


async def get_nginx(
    injector: Annotated[GatewayDependencyInjector, Depends(get_gateway_injector)],
) -> Nginx:
    return injector.get_nginx()


async def get_stats_collector(
    injector: Annotated[GatewayDependencyInjector, Depends(get_gateway_injector)],
) -> StatsCollector:
    return injector.get_stats_collector()
