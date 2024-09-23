from typing import AsyncGenerator

from dstack._internal.gateway.deps import BaseGatewayDependencyInjector
from dstack._internal.gateway.repos.base import BaseGatewayRepo
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.services.gateway_in_server.repo import DBGatewayRepo


class GatewayInServerDependencyInjector(BaseGatewayDependencyInjector):
    async def get_repo(self) -> AsyncGenerator[BaseGatewayRepo, None]:
        async with get_session_ctx() as session:
            yield DBGatewayRepo(session)
