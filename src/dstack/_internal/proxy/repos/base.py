from abc import ABC, abstractmethod
from typing import List, Optional

from dstack._internal.proxy.repos.models import ChatModel, Project, Service


class BaseProxyRepo(ABC):
    @abstractmethod
    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        pass

    @abstractmethod
    async def set_service(self, project_name: str, service: Service) -> None:
        pass

    @abstractmethod
    async def list_models(self, project_name: str) -> List[ChatModel]:
        pass

    @abstractmethod
    async def get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        pass

    @abstractmethod
    async def set_model(self, project_name: str, model: ChatModel) -> None:
        pass

    @abstractmethod
    async def get_project(self, name: str) -> Optional[Project]:
        pass

    @abstractmethod
    async def set_project(self, project: Project) -> None:
        pass

    @abstractmethod
    async def is_project_member(self, project_name: str, token: str) -> bool:
        pass
