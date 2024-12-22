from typing import Container, Optional

from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider


class ProxyTestAuthProvider(BaseProxyAuthProvider):
    def __init__(self, project_to_tokens: Optional[dict[str, Container[str]]] = None) -> None:
        self._project_to_tokens = project_to_tokens or {}

    async def is_project_member(self, project_name: str, token: str) -> bool:
        return token in self._project_to_tokens.get(project_name, set())
