from abc import ABC, abstractmethod
from typing import AsyncGenerator

from fastapi import Depends, Request
from typing_extensions import Annotated

from dstack._internal.gateway.repos.base import BaseGatewayRepo


class BaseGatewayDependencyInjector(ABC):
    """
    The gateway uses different implementations of this injector in different
    environments: in-serer and on a remote host. An instance with the injector interface
    stored in FastAPI's app.state.gateway_dependency_injector configures the gateway to
    use a specific set of dependencies, e.g. a specific repo implementation.
    """

    @abstractmethod
    async def get_repo(self) -> AsyncGenerator[BaseGatewayRepo, None]:
        if False:
            yield  # show type checkers this is a generator


async def get_injector(request: Request) -> BaseGatewayDependencyInjector:
    injector = request.app.state.gateway_dependency_injector
    if not isinstance(injector, BaseGatewayDependencyInjector):
        raise RuntimeError(f"Wrong BaseGatewayDependencyInjector type {type(injector)}")
    return injector


async def get_gateway_repo(
    injector: Annotated[BaseGatewayDependencyInjector, Depends(get_injector)],
) -> AsyncGenerator[BaseGatewayRepo, None]:
    async for repo in injector.get_repo():
        yield repo
