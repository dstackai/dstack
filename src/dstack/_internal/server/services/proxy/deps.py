from typing import AsyncGenerator

from dstack._internal.proxy.deps import BaseProxyDependencyInjector
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.services.proxy.repo import DBProxyRepo


class ServerProxyDependencyInjector(BaseProxyDependencyInjector):
    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        async with get_session_ctx() as session:
            yield DBProxyRepo(session)
