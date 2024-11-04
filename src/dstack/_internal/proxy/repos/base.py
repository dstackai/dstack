from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Annotated

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


class TGIChatModelFormat(BaseModel):
    format: Literal["tgi"]
    chat_template: str
    eos_token: str


class OpenAIChatModelFormat(BaseModel):
    format: Literal["openai"]
    prefix: str


AnyModelFormat = Union[TGIChatModelFormat, OpenAIChatModelFormat]


class ChatModel(BaseModel):
    name: str
    created_at: datetime
    run_name: str
    format_spec: Annotated[AnyModelFormat, Field(discriminator="format")]


class BaseProxyRepo(ABC):
    @abstractmethod
    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        pass

    @abstractmethod
    async def add_service(self, project_name: str, service: Service) -> None:
        pass

    @abstractmethod
    async def list_models(self, project_name: str) -> List[ChatModel]:
        pass

    @abstractmethod
    async def get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        pass

    @abstractmethod
    async def add_model(self, project_name: str, model: ChatModel) -> None:
        pass

    @abstractmethod
    async def get_project(self, name: str) -> Optional[Project]:
        pass

    @abstractmethod
    async def add_project(self, project: Project) -> None:
        pass

    @abstractmethod
    async def is_project_member(self, project_name: str, token: str) -> bool:
        pass
