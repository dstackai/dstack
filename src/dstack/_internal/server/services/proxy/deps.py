from typing import AsyncGenerator

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.deps import ProxyDependencyInjector
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.services.proxy.auth import ServerProxyAuthProvider
from dstack._internal.server.services.proxy.repo import ServerProxyRepo


class ServerProxyDependencyInjector(ProxyDependencyInjector):
    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        async with get_session_ctx() as session:
            yield ServerProxyRepo(session)

    async def get_auth_provider(self) -> AsyncGenerator[BaseProxyAuthProvider, None]:
        async with get_session_ctx() as session:
            yield ServerProxyAuthProvider(session)
