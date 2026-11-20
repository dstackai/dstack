import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProxyCaller:
    """The user who makes a request and the project the request is made in."""

    project_id: uuid.UUID
    user_id: uuid.UUID


class BaseProxyAuthProvider(ABC):
    @abstractmethod
    async def is_project_member(self, project_name: str, token: str) -> bool:
        pass

    @abstractmethod
    async def get_caller(self, project_name: str, token: str) -> Optional[ProxyCaller]:
        """
        Returns the caller if the token belongs to a member of the project or to a global admin,
        and `None` otherwise. May raise a 404 `ProxyError` if the project does not exist.
        """
        pass
