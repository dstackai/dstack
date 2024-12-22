from abc import ABC, abstractmethod
from typing import List, Optional

from dstack._internal.proxy.lib.models import ChatModel, Project, Service


class BaseProxyRepo(ABC):
    """
    Data access methods relevant for both in-server and gateway environments.
    Implementations can have additional environment-specific methods.
    """

    @abstractmethod
    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        pass

    @abstractmethod
    async def list_models(self, project_name: str) -> List[ChatModel]:
        pass

    @abstractmethod
    async def get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        pass

    @abstractmethod
    async def get_project(self, name: str) -> Optional[Project]:
        pass
