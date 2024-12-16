from abc import ABC, abstractmethod


class BaseProxyAuthProvider(ABC):
    @abstractmethod
    async def is_project_member(self, project_name: str, token: str) -> bool:
        pass
