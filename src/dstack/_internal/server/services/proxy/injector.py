from typing import AsyncGenerator

from dstack._internal.proxy.deps import BaseProxyDependencyInjector
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.services.auth.base import BaseProxyAuthProvider
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.services.proxy.auth import ServerProxyAuthProvider
from dstack._internal.server.services.proxy.repo import ServerProxyRepo


class ServerProxyDependencyInjector(BaseProxyDependencyInjector):
    async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
        async with get_session_ctx() as session:
            yield ServerProxyRepo(session)

    async def get_auth_provider(self) -> AsyncGenerator[BaseProxyAuthProvider, None]:
        async with get_session_ctx() as session:
            yield ServerProxyAuthProvider(session)
