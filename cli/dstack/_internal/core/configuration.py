from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Extra, Field, conint, constr, validator
from typing_extensions import Annotated, Literal

CommandsList = List[str]


class PythonVersion(str, Enum):
    PY37 = "3.7"
    PY38 = "3.8"
    PY39 = "3.9"
    PY310 = "3.10"
    PY311 = "3.11"


class ForbidExtra(BaseModel):
    class Config:
        extra = Extra.forbid


class RegistryAuth(ForbidExtra):
    username: Annotated[Optional[str], Field(description="Username")]
    password: Annotated[str, Field(description="Password or access token")]


class Artifact(ForbidExtra):
    path: Annotated[
        str, Field(description="The path to the folder that must be stored as an output artifact")
    ]
    mount: Annotated[
        bool,
        Field(
            description="Must be set to `true` if the artifact files must be saved in real-time"
        ),
    ] = False


class BaseConfiguration(ForbidExtra):
    type: Literal["none"]
    image: Annotated[Optional[str], Field(description="The name of the Docker image to run")]
    entrypoint: Annotated[Optional[str], Field(description="The Docker entrypoint")]
    home_dir: Annotated[
        str, Field(description="The absolute path to the home directory inside the container")
    ] = "/root"
    registry_auth: Annotated[
        Optional[RegistryAuth], Field(description="Credentials for pulling a private container")
    ]
    python: Annotated[
        Optional[PythonVersion],
        Field(description="The major version of Python\nMutually exclusive with the image"),
    ]
    ports: Annotated[
        List[Union[constr(regex=r"^[0-9]+:[0-9]+$"), conint(gt=0, le=65536)]],
        Field(description="Port numbers/mapping to expose"),
    ] = []
    env: Annotated[
        Union[List[constr(regex=r"^[a-zA-Z_][a-zA-Z0-9_]*=.*$")], Dict[str, str]],
        Field(description="The mapping or the list of environment variables"),
    ] = {}
    build: Annotated[
        CommandsList, Field(description="The bash commands to run during build stage")
    ] = []
    cache: Annotated[
        List[str], Field(description="The directories to be cached between configuration runs")
    ] = []

    @validator("python", pre=True, always=True)
    def convert_python(cls, v, values) -> Optional[PythonVersion]:
        if v is not None and values.get("image"):
            raise KeyError("`image` and `python` are mutually exclusive fields")
        if isinstance(v, float):
            v = str(v)
            if v == "3.1":
                v = "3.10"
        if isinstance(v, str):
            return PythonVersion(v)
        return v

    @validator("env")
    def convert_env(cls, v) -> Dict[str, str]:
        if isinstance(v, list):
            return dict(pair.split(sep="=", maxsplit=1) for pair in v)
        return v


class DevEnvironmentConfiguration(BaseConfiguration):
    type: Literal["dev-environment"] = "dev-environment"
    ide: Annotated[Literal["vscode"], Field(description="The IDE to run")]
    init: Annotated[CommandsList, Field(description="The bash commands to run")] = []


class TaskConfiguration(BaseConfiguration):
    type: Literal["task"] = "task"
    commands: Annotated[CommandsList, Field(description="The bash commands to run")]
    artifacts: Annotated[List[Artifact], Field(description="The list of output artifacts")] = []


class DstackConfiguration(BaseModel):
    __root__: Annotated[
        Union[DevEnvironmentConfiguration, TaskConfiguration], Field(discriminator="type")
    ]

    class Config:
        schema_extra = {"$schema": "http://json-schema.org/draft-07/schema#"}


def parse(data: dict) -> Union[DevEnvironmentConfiguration, TaskConfiguration]:
    conf = DstackConfiguration.parse_obj(data).__root__
    return conf
