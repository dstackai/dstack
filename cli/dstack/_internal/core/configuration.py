from typing import List, Optional, Union

from pydantic import BaseModel, Extra, Field, validator
from typing_extensions import Annotated, Literal

PythonVersions = Literal["3.7", "3.8", "3.9", "3.10", "3.11"]


class ForbidExtra(BaseModel):
    class Config:
        extra = Extra.forbid


class RegistryAuth(ForbidExtra):
    username: Optional[str]
    password: str


class Artifact(ForbidExtra):
    path: str
    mount: bool = False


class BaseConfiguration(ForbidExtra):
    image: Optional[str]
    registry_auth: Optional[RegistryAuth]
    python: Optional[PythonVersions]
    ports: List[Union[str, int]] = []
    env: List[str] = []
    build: List[str] = []
    cache: List[str] = []

    @validator("python", pre=True)
    def convert_python(cls, v) -> str:
        if isinstance(v, float):
            v = str(v)
            if v == "3.1":
                v = "3.10"
        return v


class DevEnvironmentConfiguration(BaseConfiguration):
    type: Literal["dev-environment"] = "dev-environment"
    ide: Literal["vscode"]
    init: List[str] = []


class TaskConfiguration(BaseConfiguration):
    type: Literal["task"] = "task"
    commands: List[str]
    artifacts: List[Artifact] = []


class DstackConfiguration(BaseModel):
    __root__: Annotated[
        Union[DevEnvironmentConfiguration, TaskConfiguration], Field(discriminator="type")
    ]


def parse(data: dict) -> Union[DevEnvironmentConfiguration, TaskConfiguration]:
    return DstackConfiguration.parse_obj(data).__root__
