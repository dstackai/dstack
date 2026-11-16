from abc import ABC, abstractmethod

from dstack._internal.proxy.lib.schemas.usage import AuthorizedSubject


class BaseProxyAuthProvider(ABC):
    @abstractmethod
    async def is_project_member(self, project_name: str, token: str) -> bool:
        pass

    async def resolve_subject(self, project_name: str, token: str) -> AuthorizedSubject | None:
        return None
