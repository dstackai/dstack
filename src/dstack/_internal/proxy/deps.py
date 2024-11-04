from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from fastapi import Depends, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing_extensions import Annotated

from dstack._internal.proxy.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.repos.base import BaseProxyRepo


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


async def get_injector(request: Request) -> BaseProxyDependencyInjector:
    injector = request.app.state.proxy_dependency_injector
    if not isinstance(injector, BaseProxyDependencyInjector):
        raise UnexpectedProxyError(f"Unexpected proxy_dependency_injector type {type(injector)}")
    return injector


async def get_proxy_repo(
    injector: Annotated[BaseProxyDependencyInjector, Depends(get_injector)],
) -> AsyncGenerator[BaseProxyRepo, None]:
    async for repo in injector.get_repo():
        yield repo


class ProxyAuthContext:
    def __init__(self, project_name: str, token: Optional[str], repo: BaseProxyRepo):
        self._project_name = project_name
        self._token = token
        self._repo = repo

    async def enforce(self) -> None:
        if self._token is None or not await self._repo.is_project_member(
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
        repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    ) -> ProxyAuthContext:
        context = ProxyAuthContext(
            project_name=project_name,
            token=token.credentials if token is not None else None,
            repo=repo,
        )
        if self._auto_enforce:
            await context.enforce()
        return context
