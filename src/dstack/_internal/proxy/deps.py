from abc import ABC, abstractmethod
from typing import AsyncGenerator

from fastapi import Depends, Request
from typing_extensions import Annotated

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
        raise RuntimeError(f"Wrong BaseProxyDependencyInjector type {type(injector)}")
    return injector


async def get_proxy_repo(
    injector: Annotated[BaseProxyDependencyInjector, Depends(get_injector)],
) -> AsyncGenerator[BaseProxyRepo, None]:
    async for repo in injector.get_repo():
        yield repo
