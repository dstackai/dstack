import re
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, ValidationError, conint, constr, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import ForbidExtra
from dstack._internal.core.models.gateways import AnyModel
from dstack._internal.core.models.repos.base import Repo
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack._internal.core.models.resources import ResourcesSpec

CommandsList = List[str]
ValidPort = conint(gt=0, le=65536)


class ConfigurationType(str, Enum):
    DEV_ENVIRONMENT = "dev-environment"
    TASK = "task"
    SERVICE = "service"


class PythonVersion(str, Enum):
    PY38 = "3.8"
    PY39 = "3.9"
    PY310 = "3.10"
    PY311 = "3.11"


class RegistryAuth(ForbidExtra):
    """
    Credentials for pulling a private Docker image.

    Attributes:
        username (str): The username
        password (str): The password or access token
    """

    username: Annotated[Optional[str], Field(description="The username")]
    password: Annotated[str, Field(description="The password or access token")]


class PortMapping(ForbidExtra):
    local_port: Optional[ValidPort] = None
    container_port: ValidPort

    @classmethod
    def parse(cls, v: str) -> "PortMapping":
        """
        Possible values:
          - 8080
          - 80:8080
          - *:8080
        """
        r = re.search(r"^(?:(\d+|\*):)?(\d+)?$", v)
        if not r:
            raise ValueError(v)
        local_port, container_port = r.groups()
        if local_port is None:  # identity mapping by default
            local_port = int(container_port)
        elif local_port == "*":
            local_port = None
        else:
            local_port = int(local_port)
        return PortMapping(local_port=local_port, container_port=int(container_port))


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
        Optional[RegistryAuth], Field(description="Credentials for pulling a private Docker image")
    ]
    python: Annotated[
        Optional[PythonVersion],
        Field(description="The major version of Python\nMutually exclusive with the image"),
    ]
    env: Annotated[
        Union[List[constr(regex=r"^[a-zA-Z_][a-zA-Z0-9_]*=.*$")], Dict[str, str]],
        Field(description="The mapping or the list of environment variables"),
    ] = {}
    setup: Annotated[CommandsList, Field(description="The bash commands to run on the boot")] = []
    resources: Annotated[
        ResourcesSpec, Field(description="The resources requirements to run the configuration")
    ] = ResourcesSpec()

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

    def get_repo(self) -> Repo:
        return VirtualRepo(repo_id="none")


class BaseConfigurationWithPorts(BaseConfiguration):
    ports: Annotated[
        List[Union[ValidPort, constr(regex=r"^(?:[0-9]+|\*):[0-9]+$"), PortMapping]],
        Field(description="Port numbers/mapping to expose"),
    ] = []

    @validator("ports", each_item=True)
    def convert_ports(cls, v) -> PortMapping:
        if isinstance(v, int):
            return PortMapping(local_port=v, container_port=v)
        elif isinstance(v, str):
            return PortMapping.parse(v)
        return v


class DevEnvironmentConfiguration(BaseConfigurationWithPorts):
    type: Literal["dev-environment"] = "dev-environment"
    ide: Annotated[Literal["vscode"], Field(description="The IDE to run")]
    version: Annotated[Optional[str], Field(description="The version of the IDE")]
    init: Annotated[CommandsList, Field(description="The bash commands to run")] = []


class TaskConfiguration(BaseConfigurationWithPorts):
    """
    Attributes:
        commands (List[str]): The bash commands to run
        ports (List[PortMapping]): Port numbers/mapping to expose
        env (Dict[str, str]): The mapping or the list of environment variables
        image (Optional[str]): The name of the Docker image to run
        python (Optional[str]): The major version of Python
        entrypoint (Optional[str]): The Docker entrypoint
        registry_auth (Optional[RegistryAuth]): Credentials for pulling a private Docker image
        home_dir (str): The absolute path to the home directory inside the container. Defaults to `/root`.
        resources (Optional[ResourcesSpec]): The requirements to run the configuration.
    """

    type: Literal["task"] = "task"
    commands: Annotated[CommandsList, Field(description="The bash commands to run")]


class ServiceConfiguration(BaseConfiguration):
    """
    Attributes:
        commands (List[str]): The bash commands to run
        port (PortMapping): The port, that application listens to or the mapping
        env (Dict[str, str]): The mapping or the list of environment variables
        image (Optional[str]): The name of the Docker image to run
        python (Optional[str]): The major version of Python
        entrypoint (Optional[str]): The Docker entrypoint
        registry_auth (Optional[RegistryAuth]): Credentials for pulling a private Docker image
        home_dir (str): The absolute path to the home directory inside the container. Defaults to `/root`.
        resources (Optional[ResourcesSpec]): The requirements to run the configuration.
        model (Optional[ModelMapping]): Mapping of the model for the OpenAI-compatible endpoint.
        auth (bool): Enable the authorization. Defaults to `True`.
    """

    type: Literal["service"] = "service"
    commands: Annotated[CommandsList, Field(description="The bash commands to run")]
    port: Annotated[
        Union[ValidPort, constr(regex=r"^[0-9]+:[0-9]+$"), PortMapping],
        Field(description="The port, that application listens to or the mapping"),
    ]
    model: Annotated[
        Optional[AnyModel],
        Field(description="Mapping of the model for the OpenAI-compatible endpoint"),
    ] = None
    auth: Annotated[bool, Field(description="Enable the authorization")] = True

    @validator("port")
    def convert_port(cls, v) -> PortMapping:
        if isinstance(v, int):
            return PortMapping(local_port=80, container_port=v)
        elif isinstance(v, str):
            return PortMapping.parse(v)
        return v


AnyRunConfiguration = Union[DevEnvironmentConfiguration, TaskConfiguration, ServiceConfiguration]


class RunConfiguration(BaseModel):
    __root__: Annotated[
        AnyRunConfiguration,
        Field(discriminator="type"),
    ]

    class Config:
        schema_extra = {"$schema": "http://json-schema.org/draft-07/schema#"}


def parse(data: dict) -> AnyRunConfiguration:
    try:
        conf = RunConfiguration.parse_obj(data).__root__
    except ValidationError as e:
        raise ConfigurationError(e)
    return conf
