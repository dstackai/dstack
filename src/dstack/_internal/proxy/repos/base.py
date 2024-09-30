from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.instances import SSHConnectionParams


class Replica(BaseModel):
    id: str
    ssh_destination: str
    ssh_port: int
    ssh_proxy: Optional[SSHConnectionParams]


class Service(BaseModel):
    id: str
    run_name: str
    auth: bool
    app_port: int
    replicas: List[Replica]


class Project(BaseModel):
    name: str
    ssh_private_key: str


class BaseProxyRepo(ABC):
    @abstractmethod
    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        pass

    @abstractmethod
    async def add_service(self, project_name: str, service: Service) -> None:
        pass

    @abstractmethod
    async def get_project(self, name: str) -> Optional[Project]:
        pass

    @abstractmethod
    async def add_project(self, project: Project) -> None:
        pass
