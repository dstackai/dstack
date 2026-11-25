from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider, ProxyCaller
from dstack._internal.server.security.permissions import get_project_member, is_project_member


class ServerProxyAuthProvider(BaseProxyAuthProvider):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_project_member(self, project_name: str, token: str) -> bool:
        return await is_project_member(self.session, project_name, token)

    async def get_caller(self, project_name: str, token: str) -> Optional[ProxyCaller]:
        try:
            user, project = await get_project_member(self.session, project_name, token)
        except HTTPException:
            return None
        return ProxyCaller(project_id=project.id, user_id=user.id)
