from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.server.security.permissions import is_project_member


class ServerProxyAuthProvider(BaseProxyAuthProvider):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_project_member(self, project_name: str, token: str) -> bool:
        return await is_project_member(self.session, project_name, token)
