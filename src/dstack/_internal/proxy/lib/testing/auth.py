import uuid
from typing import Container, Optional

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider, ProxyCaller


class ProxyTestAuthProvider(BaseProxyAuthProvider):
    def __init__(self, project_to_tokens: Optional[dict[str, Container[str]]] = None) -> None:
        self._project_to_tokens = project_to_tokens or {}

    async def is_project_member(self, project_name: str, token: str) -> bool:
        return token in self._project_to_tokens.get(project_name, set())

    async def get_caller(self, project_name: str, token: str) -> Optional[ProxyCaller]:
        if not await self.is_project_member(project_name, token):
            return None
        return make_caller(project_name, token)


def make_caller(project_name: str, token: str) -> ProxyCaller:
    """IDs are derived from the project name and the token, so tests can tell callers apart."""
    return ProxyCaller(
        project_id=uuid.uuid5(uuid.NAMESPACE_DNS, project_name),
        user_id=uuid.uuid5(uuid.NAMESPACE_DNS, token),
    )
