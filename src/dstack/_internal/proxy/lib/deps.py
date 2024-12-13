from abc import ABC
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing_extensions import Annotated

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.lib.repo import BaseProxyRepo


class ProxyDependencyInjector(ABC):
    """
    An injector instance stored in FastAPI's app.state.proxy_dependency_injector
    configures dstack-proxy to use a specific set of dependencies, e.g.
    a specific repo implementation.
    """

    def __init__(self, repo: BaseProxyRepo, auth: BaseProxyAuthProvider) -> None:
        self._repo = repo
        self._auth = auth

    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        yield self._repo

    async def get_auth_provider(self) -> AsyncGenerator[BaseProxyAuthProvider, None]:
        yield self._auth


def get_injector_from_app(app: FastAPI) -> ProxyDependencyInjector:
    injector = app.state.proxy_dependency_injector
    if not isinstance(injector, ProxyDependencyInjector):
        raise UnexpectedProxyError(f"Unexpected proxy_dependency_injector type {type(injector)}")
    return injector


async def get_injector(request: Request) -> ProxyDependencyInjector:
    return get_injector_from_app(request.app)


async def get_proxy_repo(
    injector: Annotated[ProxyDependencyInjector, Depends(get_injector)],
) -> AsyncGenerator[BaseProxyRepo, None]:
    async for repo in injector.get_repo():
        yield repo


async def get_proxy_auth_provider(
    injector: Annotated[ProxyDependencyInjector, Depends(get_injector)],
) -> AsyncGenerator[BaseProxyAuthProvider, None]:
    async for provider in injector.get_auth_provider():
        yield provider


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
