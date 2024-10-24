from typing import Container, Dict, Optional

from dstack._internal.proxy.repos.memory import InMemoryProxyRepo


class ProxyTestRepo(InMemoryProxyRepo):
    def __init__(self, project_to_tokens: Optional[Dict[str, Container[str]]] = None) -> None:
        super().__init__()
        self._project_to_tokens = project_to_tokens or {}

    async def is_project_member(self, project_name: str, token: str) -> bool:
        return token in self._project_to_tokens.get(project_name, set())
