from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing_extensions import Annotated

from dstack._internal.proxy.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.repos.gateway import GatewayProxyRepo
from dstack._internal.proxy.services.auth.base import BaseProxyAuthProvider
from dstack._internal.proxy.services.nginx import Nginx
from dstack._internal.proxy.services.stats import StatsCollector


class BaseProxyDependencyInjector(ABC):
    """
    dstack-proxy uses different implementations of this injector in different
    environments: within dstack-serer and on a gateway instance. An object with
    the injector interface stored in FastAPI's
    app.state.proxy_dependency_injector configures dstack-proxy to use a
    specific set of dependencies, e.g. a specific repo implementation.
    """

    @abstractmethod
    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        if False:
            yield  # show type checkers this is a generator

    @abstractmethod
    async def get_auth_provider(self) -> AsyncGenerator[BaseProxyAuthProvider, None]:
        if False:
            yield  # show type checkers this is a generator

    async def get_nginx(self) -> Optional[Nginx]:
        return None

    async def get_stats_collector(self) -> Optional[StatsCollector]:
        return None


def get_injector_from_app(app: FastAPI) -> BaseProxyDependencyInjector:
    injector = app.state.proxy_dependency_injector
    if not isinstance(injector, BaseProxyDependencyInjector):
        raise UnexpectedProxyError(f"Unexpected proxy_dependency_injector type {type(injector)}")
    return injector


async def get_injector(request: Request) -> BaseProxyDependencyInjector:
    return get_injector_from_app(request.app)


async def get_proxy_repo(
    injector: Annotated[BaseProxyDependencyInjector, Depends(get_injector)],
) -> AsyncGenerator[BaseProxyRepo, None]:
    async for repo in injector.get_repo():
        yield repo


async def get_gateway_proxy_repo(
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
) -> GatewayProxyRepo:
    if not isinstance(repo, GatewayProxyRepo):
        raise UnexpectedProxyError(f"Unexpected gateway repo type: {type(repo)}")
    return repo


async def get_proxy_auth_provider(
    injector: Annotated[BaseProxyDependencyInjector, Depends(get_injector)],
) -> AsyncGenerator[BaseProxyAuthProvider, None]:
    async for provider in injector.get_auth_provider():
        yield provider


async def get_nginx(
    injector: Annotated[BaseProxyDependencyInjector, Depends(get_injector)],
) -> Nginx:
    nginx = await injector.get_nginx()
    if nginx is None:
        raise UnexpectedProxyError("Nginx is not available")
    return nginx


async def get_stats_collector(
    injector: Annotated[BaseProxyDependencyInjector, Depends(get_injector)],
) -> StatsCollector:
    stats_collector = await injector.get_stats_collector()
    if stats_collector is None:
        raise UnexpectedProxyError("StatsCollector is not available")
    return stats_collector


class ProxyAuthContext:
    def __init__(self, project_name: str, token: Optional[str], provider: BaseProxyAuthProvider):
        self._project_name = project_name
        self._token = token
        self._provider = provider

    async def enforce(self) -> None:
        if self._token is None or not await self._provider.is_project_member(
            self._project_name, self._token
        ):
            raise ProxyError(
                f"Unauthenticated or unauthorized to access project {self._project_name}",
                status.HTTP_403_FORBIDDEN,
            )


class ProxyAuth:
    def __init__(self, auto_enforce: bool):
        self._auto_enforce = auto_enforce

    async def __call__(
        self,
        project_name: str,
        token: Annotated[
            Optional[HTTPAuthorizationCredentials], Security(HTTPBearer(auto_error=False))
        ],
        provider: Annotated[BaseProxyAuthProvider, Depends(get_proxy_auth_provider)],
    ) -> ProxyAuthContext:
        context = ProxyAuthContext(
            project_name=project_name,
            token=token.credentials if token is not None else None,
            provider=provider,
        )
        if self._auto_enforce:
            await context.enforce()
        return context
