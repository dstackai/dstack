import re
import string
from collections import Counter
from enum import Enum
from pathlib import PurePosixPath
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

import orjson
from pydantic import Field, ValidationError, conint, constr, root_validator, validator
from typing_extensions import Self

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import CoreModel, Duration, RegistryAuth
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.files import FilePathMapping
from dstack._internal.core.models.fleets import FleetConfiguration
from dstack._internal.core.models.gateways import GatewayConfiguration
from dstack._internal.core.models.profiles import ProfileParams, parse_duration, parse_off_duration
from dstack._internal.core.models.resources import Range, ResourcesSpec
from dstack._internal.core.models.services import AnyModel, OpenAIChatModel
from dstack._internal.core.models.unix import UnixUser
from dstack._internal.core.models.volumes import MountPoint, VolumeConfiguration, parse_mount_point
from dstack._internal.utils.common import has_duplicates
from dstack._internal.utils.json_schema import add_extra_schema_types
from dstack._internal.utils.json_utils import (
    pydantic_orjson_dumps_with_indent,
)

CommandsList = List[str]
ValidPort = conint(gt=0, le=65536)
MAX_INT64 = 2**63 - 1
SERVICE_HTTPS_DEFAULT = True
STRIP_PREFIX_DEFAULT = True
RUN_PRIOTIRY_MIN = 0
RUN_PRIOTIRY_MAX = 100
RUN_PRIORITY_DEFAULT = 0
DEFAULT_REPO_DIR = "/workflow"
MIN_PROBE_TIMEOUT = 1
MIN_PROBE_INTERVAL = 1
DEFAULT_PROBE_URL = "/"
DEFAULT_PROBE_TIMEOUT = 10
DEFAULT_PROBE_INTERVAL = 15
DEFAULT_PROBE_READY_AFTER = 1
DEFAULT_PROBE_METHOD = "get"
MAX_PROBE_URL_LEN = 2048


class RunConfigurationType(str, Enum):
    DEV_ENVIRONMENT = "dev-environment"
    TASK = "task"
    SERVICE = "service"


class PythonVersion(str, Enum):
    PY39 = "3.9"
    PY310 = "3.10"
    PY311 = "3.11"
    PY312 = "3.12"
    PY313 = "3.13"


class PortMapping(CoreModel):
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


class RepoSpec(CoreModel):
    local_path: Annotated[
        Optional[str],
        Field(
            description=(
                "The path to the Git repo on the user's machine. Relative paths are resolved"
                " relative to the parent directory of the the configuration file."
                " Mutually exclusive with `url`"
            )
        ),
    ] = None
    url: Annotated[
        Optional[str],
        Field(description="The Git repo URL. Mutually exclusive with `local_path`"),
    ] = None
    branch: Annotated[
        Optional[str],
        Field(
            description=(
                "The repo branch. Defaults to the active branch for local paths"
                " and the default branch for URLs"
            )
        ),
    ] = None
    hash: Annotated[
        Optional[str],
        Field(description="The commit hash"),
    ] = None
    # Not implemented, has no effect, hidden in the docs
    path: str = DEFAULT_REPO_DIR

    @classmethod
    def parse(cls, v: str) -> Self:
        is_url = False
        parts = v.split(":")
        if len(parts) > 1:
            # Git repo, git@github.com:dstackai/dstack.git or https://github.com/dstackai/dstack
            if "@" in parts[0] or parts[1].startswith("//"):
                parts = [f"{parts[0]}:{parts[1]}", *parts[2:]]
                is_url = True
            # Windows path, e.g., `C:\path\to`, 'c:/path/to'
            elif (
                len(parts[0]) == 1
                and parts[0] in string.ascii_letters
                and parts[1][:1] in ["\\", "/"]
            ):
                parts = [f"{parts[0]}:{parts[1]}", *parts[2:]]
        if len(parts) == 1:
            if is_url:
                return cls(url=parts[0])
            return cls(local_path=parts[0])
        if len(parts) == 2:
            if is_url:
                return cls(url=parts[0], path=parts[1])
            return cls(local_path=parts[0], path=parts[1])
        raise ValueError(f"Invalid repo: {v}")

    @root_validator
    def validate_local_path_or_url(cls, values):
        if values["local_path"] and values["url"]:
            raise ValueError("`local_path` and `url` are mutually exclusive")
        if not values["local_path"] and not values["url"]:
            raise ValueError("Either `local_path` or `url` must be specified")
        return values


class ScalingSpec(CoreModel):
    metric: Annotated[
        Literal["rps"],
        Field(
            description="The target metric to track. Currently, the only supported value is `rps` "
            "(meaning requests per second)"
        ),
    ]
    target: Annotated[
        float,
        Field(
            description="The target value of the metric. "
            "The number of replicas is calculated based on this number and automatically adjusts "
            "(scales up or down) as this metric changes",
            gt=0,
        ),
    ]
    scale_up_delay: Annotated[
        Duration, Field(description="The delay in seconds before scaling up")
    ] = Duration.parse("5m")
    scale_down_delay: Annotated[
        Duration, Field(description="The delay in seconds before scaling down")
    ] = Duration.parse("10m")


class IPAddressPartitioningKey(CoreModel):
    type: Annotated[Literal["ip_address"], Field(description="Partitioning type")] = "ip_address"


class HeaderPartitioningKey(CoreModel):
    type: Annotated[Literal["header"], Field(description="Partitioning type")] = "header"
    header: Annotated[
        str,
        Field(
            description="Name of the header to use for partitioning",
            regex=r"^[a-zA-Z0-9-_]+$",  # prevent Nginx config injection
            max_length=500,  # chosen randomly, Nginx limit is higher
        ),
    ]


class RateLimit(CoreModel):
    prefix: Annotated[
        str,
        Field(
            description=(
                "URL path prefix to which this limit is applied."
                " If an incoming request matches several prefixes, the longest prefix is applied"
            ),
            max_length=4094,  # Nginx limit
            regex=r"^/[^\s\\{}]*$",  # prevent Nginx config injection
        ),
    ] = "/"
    key: Annotated[
        Union[IPAddressPartitioningKey, HeaderPartitioningKey],
        Field(
            discriminator="type",
            description=(
                "The partitioning key. Each incoming request belongs to a partition"
                " and rate limits are applied per partition."
                " Defaults to partitioning by client IP address"
            ),
        ),
    ] = IPAddressPartitioningKey()
    rps: Annotated[
        float,
        Field(
            description=(
                "Max allowed number of requests per second."
                " Requests are tracked at millisecond granularity."
                " For example, `rps: 10` means at most 1 request per 100ms"
            ),
            # should fit into Nginx limits after being converted to requests per minute
            ge=1 / 60,
            le=MAX_INT64 // 60,
        ),
    ]
    burst: Annotated[
        int,
        Field(
            ge=0,
            le=MAX_INT64,  # Nginx limit
            description=(
                "Max number of requests that can be passed to the service ahead of the rate limit"
            ),
        ),
    ] = 0


HTTPMethod = Literal["get", "post", "put", "delete", "patch", "head"]


class HTTPHeaderSpec(CoreModel):
    name: Annotated[
        str,
        Field(
            description="The name of the HTTP header",
            min_length=1,
            max_length=256,
        ),
    ]
    value: Annotated[
        str,
        Field(
            description="The value of the HTTP header",
            min_length=1,
            max_length=2048,
        ),
    ]


class ProbeConfig(CoreModel):
    type: Literal["http"]  # expect other probe types in the future, namely `exec`
    url: Annotated[
        Optional[str], Field(description=f"The URL to request. Defaults to `{DEFAULT_PROBE_URL}`")
    ] = None
    method: Annotated[
        Optional[HTTPMethod],
        Field(
            description=(
                "The HTTP method to use for the probe (e.g., `get`, `post`, etc.)."
                f" Defaults to `{DEFAULT_PROBE_METHOD}`"
            )
        ),
    ] = None
    headers: Annotated[
        list[HTTPHeaderSpec],
        Field(description="A list of HTTP headers to include in the request", max_items=16),
    ] = []
    body: Annotated[
        Optional[str],
        Field(
            description="The HTTP request body to send with the probe",
            min_length=1,
            max_length=2048,
        ),
    ] = None
    timeout: Annotated[
        Optional[int],
        Field(
            description=(
                f"Maximum amount of time the HTTP request is allowed to take. Defaults to `{DEFAULT_PROBE_TIMEOUT}s`"
            )
        ),
    ] = None
    interval: Annotated[
        Optional[int],
        Field(
            description=(
                "Minimum amount of time between the end of one probe execution"
                f" and the start of the next. Defaults to `{DEFAULT_PROBE_INTERVAL}s`"
            )
        ),
    ] = None
    ready_after: Annotated[
        Optional[int],
        Field(
            ge=1,
            description=(
                "The number of consecutive successful probe executions required for the replica"
                " to be considered ready. Used during rolling deployments."
                f" Defaults to `{DEFAULT_PROBE_READY_AFTER}`"
            ),
        ),
    ] = None

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            add_extra_schema_types(
                schema["properties"]["timeout"],
                extra_types=[{"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["interval"],
                extra_types=[{"type": "string"}],
            )

    @validator("timeout", pre=True)
    def parse_timeout(cls, v: Optional[Union[int, str]]) -> Optional[int]:
        if v is None:
            return v
        parsed = parse_duration(v)
        if parsed < MIN_PROBE_TIMEOUT:
            raise ValueError(f"Probe timeout cannot be shorter than {MIN_PROBE_TIMEOUT}s")
        return parsed

    @validator("interval", pre=True)
    def parse_interval(cls, v: Optional[Union[int, str]]) -> Optional[int]:
        if v is None:
            return v
        parsed = parse_duration(v)
        if parsed < MIN_PROBE_INTERVAL:
            raise ValueError(f"Probe interval cannot be shorter than {MIN_PROBE_INTERVAL}s")
        return parsed

    @validator("url")
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.startswith("/"):
            raise ValueError("Must start with `/`")
        if len(v) > MAX_PROBE_URL_LEN:
            raise ValueError(f"Cannot be longer than {MAX_PROBE_URL_LEN} characters")
        if not v.isprintable():
            raise ValueError("Cannot contain non-printable characters")
        return v

    @root_validator
    def validate_body_matches_method(cls, values):
        method: HTTPMethod = values["method"]
        if values["body"] is not None and method in ["get", "head"]:
            raise ValueError(f"Cannot set request body for the `{method}` method")
        return values


class BaseRunConfiguration(CoreModel):
    type: Literal["none"]
    name: Annotated[
        Optional[str],
        Field(description="The run name. If not specified, a random name is generated"),
    ] = None
    image: Annotated[Optional[str], Field(description="The name of the Docker image to run")] = (
        None
    )
    user: Annotated[
        Optional[str],
        Field(
            description=(
                "The user inside the container, `user_name_or_id[:group_name_or_id]`"
                " (e.g., `ubuntu`, `1000:1000`). Defaults to the default `image` user"
            )
        ),
    ] = None
    privileged: Annotated[bool, Field(description="Run the container in privileged mode")] = False
    entrypoint: Annotated[Optional[str], Field(description="The Docker entrypoint")] = None
    working_dir: Annotated[
        Optional[str],
        Field(
            description=(
                "The path to the working directory inside the container."
                f" It's specified relative to the repository directory (`{DEFAULT_REPO_DIR}`) and should be inside it."
                ' Defaults to `"."` '
            )
        ),
    ] = None
    # deprecated since 0.18.31; has no effect
    home_dir: str = "/root"
    registry_auth: Annotated[
        Optional[RegistryAuth], Field(description="Credentials for pulling a private Docker image")
    ] = None
    python: Annotated[
        Optional[PythonVersion],
        Field(
            description="The major version of Python. Mutually exclusive with `image` and `docker`"
        ),
    ] = None
    nvcc: Annotated[
        Optional[bool],
        Field(
            description="Use image with NVIDIA CUDA Compiler (NVCC) included. Mutually exclusive with `image` and `docker`"
        ),
    ] = None
    single_branch: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether to clone and track only the current branch or all remote branches."
                " Relevant only when using remote Git repos."
                " Defaults to `false` for dev environments and to `true` for tasks and services"
            )
        ),
    ] = None
    env: Annotated[
        Env,
        Field(description="The mapping or the list of environment variables"),
    ] = Env()
    shell: Annotated[
        Optional[str],
        Field(
            description=(
                "The shell used to run commands."
                " Allowed values are `sh`, `bash`, or an absolute path, e.g., `/usr/bin/zsh`."
                " Defaults to `/bin/sh` if the `image` is specified, `/bin/bash` otherwise"
            )
        ),
    ] = None
    resources: Annotated[
        ResourcesSpec, Field(description="The resources requirements to run the configuration")
    ] = ResourcesSpec()
    priority: Annotated[
        Optional[int],
        Field(
            ge=RUN_PRIOTIRY_MIN,
            le=RUN_PRIOTIRY_MAX,
            description=(
                f"The priority of the run, an integer between `{RUN_PRIOTIRY_MIN}` and `{RUN_PRIOTIRY_MAX}`."
                " `dstack` tries to provision runs with higher priority first."
                f" Defaults to `{RUN_PRIORITY_DEFAULT}`"
            ),
        ),
    ] = None
    volumes: Annotated[List[MountPoint], Field(description="The volumes mount points")] = []
    docker: Annotated[
        Optional[bool],
        Field(
            description="Use Docker inside the container. Mutually exclusive with `image`, `python`, and `nvcc`. Overrides `privileged`"
        ),
    ] = None
    repos: Annotated[
        list[RepoSpec],
        Field(description="The list of Git repos"),
    ] = []
    files: Annotated[
        list[FilePathMapping],
        Field(description="The local to container file path mappings"),
    ] = []
    # deprecated since 0.18.31; task, service -- no effect; dev-environment -- executed right before `init`
    setup: CommandsList = []

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            add_extra_schema_types(
                schema["properties"]["volumes"]["items"],
                extra_types=[{"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["files"]["items"],
                extra_types=[{"type": "string"}],
            )

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

    @validator("docker", pre=True, always=True)
    def _docker(cls, v, values) -> Optional[bool]:
        if v is True and values.get("image"):
            raise KeyError("`image` and `docker` are mutually exclusive fields")
        if v is True and values.get("python"):
            raise KeyError("`python` and `docker` are mutually exclusive fields")
        if v is True and values.get("nvcc"):
            raise KeyError("`nvcc` and `docker` are mutually exclusive fields")
        # Ideally, we'd like to also prohibit privileged=False when docker=True,
        #   but it's not possible to do so without breaking backwards compatibility.
        return v

    @validator("volumes", each_item=True, pre=True)
    def convert_volumes(cls, v: Union[MountPoint, str]) -> MountPoint:
        if isinstance(v, str):
            return parse_mount_point(v)
        return v

    @validator("files", each_item=True, pre=True)
    def convert_files(cls, v: Union[FilePathMapping, str]) -> FilePathMapping:
        if isinstance(v, str):
            return FilePathMapping.parse(v)
        return v

    @validator("repos", pre=True, each_item=True)
    def convert_repos(cls, v: Union[RepoSpec, str]) -> RepoSpec:
        if isinstance(v, str):
            return RepoSpec.parse(v)
        return v

    @validator("repos")
    def validate_repos(cls, v) -> RepoSpec:
        if len(v) > 1:
            raise ValueError("A maximum of one repo is currently supported")
        return v

    @validator("user")
    def validate_user(cls, v) -> Optional[str]:
        if v is None:
            return None
        UnixUser.parse(v)
        return v

    @validator("shell")
    def validate_shell(cls, v) -> Optional[str]:
        if v is None:
            return None
        if v in ["sh", "bash"]:
            return v
        path = PurePosixPath(v)
        if path.is_absolute():
            return v
        raise ValueError("The value must be `sh`, `bash`, or an absolute path")


class ConfigurationWithPortsParams(CoreModel):
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


class ConfigurationWithCommandsParams(CoreModel):
    commands: Annotated[CommandsList, Field(description="The shell commands to run")] = []

    @root_validator
    def check_image_or_commands_present(cls, values):
        if not values.get("commands") and not values.get("image"):
            raise ValueError("Either `commands` or `image` must be set")
        return values


class DevEnvironmentConfigurationParams(CoreModel):
    ide: Annotated[
        Union[Literal["vscode"], Literal["cursor"]],
        Field(description="The IDE to run. Supported values include `vscode` and `cursor`"),
    ]
    version: Annotated[Optional[str], Field(description="The version of the IDE")] = None
    init: Annotated[CommandsList, Field(description="The shell commands to run on startup")] = []
    inactivity_duration: Annotated[
        Optional[Union[Literal["off"], int, bool, str]],
        Field(
            description=(
                "The maximum amount of time the dev environment can be inactive"
                " (e.g., `2h`, `1d`, etc)."
                " After it elapses, the dev environment is automatically stopped."
                " Inactivity is defined as the absence of SSH connections to the"
                " dev environment, including VS Code connections, `ssh <run name>`"
                " shells, and attached `dstack apply` or `dstack attach` commands."
                " Use `off` for unlimited duration. Can be updated in-place."
                " Defaults to `off`"
            )
        ),
    ] = None

    @validator("inactivity_duration", pre=True, allow_reuse=True)
    def parse_inactivity_duration(
        cls, v: Optional[Union[Literal["off"], int, bool, str]]
    ) -> Optional[int]:
        v = parse_off_duration(v)
        if isinstance(v, int):
            return v
        return None


class DevEnvironmentConfiguration(
    ProfileParams,
    BaseRunConfiguration,
    ConfigurationWithPortsParams,
    DevEnvironmentConfigurationParams,
):
    type: Literal["dev-environment"] = "dev-environment"

    class Config(ProfileParams.Config, BaseRunConfiguration.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            ProfileParams.Config.schema_extra(schema)
            BaseRunConfiguration.Config.schema_extra(schema)

    @validator("entrypoint")
    def validate_entrypoint(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            raise ValueError("entrypoint is not supported for dev-environment")
        return v


class TaskConfigurationParams(CoreModel):
    nodes: Annotated[int, Field(description="Number of nodes", ge=1)] = 1


class TaskConfiguration(
    ProfileParams,
    BaseRunConfiguration,
    ConfigurationWithCommandsParams,
    ConfigurationWithPortsParams,
    TaskConfigurationParams,
):
    type: Literal["task"] = "task"

    class Config(ProfileParams.Config, BaseRunConfiguration.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            ProfileParams.Config.schema_extra(schema)
            BaseRunConfiguration.Config.schema_extra(schema)


class ServiceConfigurationParams(CoreModel):
    port: Annotated[
        # NOTE: it's a PortMapping for historical reasons. Only `port.container_port` is used.
        Union[ValidPort, constr(regex=r"^[0-9]+:[0-9]+$"), PortMapping],
        Field(description="The port the application listens on"),
    ]
    gateway: Annotated[
        Optional[Union[bool, str]],
        Field(
            description=(
                "The name of the gateway. Specify boolean `false` to run without a gateway."
                " Omit to run with the default gateway"
            ),
        ),
    ] = None
    strip_prefix: Annotated[
        bool,
        Field(
            description=(
                "Strip the `/proxy/services/<project name>/<run name>/` path prefix"
                " when forwarding requests to the service. Only takes effect"
                " when running the service without a gateway"
            )
        ),
    ] = STRIP_PREFIX_DEFAULT
    model: Annotated[
        Optional[AnyModel],
        Field(
            description=(
                "Mapping of the model for the OpenAI-compatible endpoint provided by `dstack`."
                " Can be a full model format definition or just a model name."
                " If it's a name, the service is expected to expose an OpenAI-compatible"
                " API at the `/v1` path"
            )
        ),
    ] = None
    https: Annotated[bool, Field(description="Enable HTTPS if running with a gateway")] = (
        SERVICE_HTTPS_DEFAULT
    )
    auth: Annotated[bool, Field(description="Enable the authorization")] = True
    replicas: Annotated[
        Range[int],
        Field(
            description="The number of replicas. Can be a number (e.g. `2`) or a range (`0..4` or `1..8`). "
            "If it's a range, the `scaling` property is required"
        ),
    ] = Range[int](min=1, max=1)
    scaling: Annotated[
        Optional[ScalingSpec],
        Field(description="The auto-scaling rules. Required if `replicas` is set to a range"),
    ] = None
    rate_limits: Annotated[list[RateLimit], Field(description="Rate limiting rules")] = []
    probes: Annotated[
        list[ProbeConfig],
        Field(description="List of probes used to determine job health"),
    ] = []

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            add_extra_schema_types(
                schema["properties"]["replicas"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["model"],
                extra_types=[{"type": "string"}],
            )

    @validator("port")
    def convert_port(cls, v) -> PortMapping:
        if isinstance(v, int):
            return PortMapping(local_port=80, container_port=v)
        elif isinstance(v, str):
            return PortMapping.parse(v)
        return v

    @validator("model", pre=True)
    def convert_model(cls, v: Optional[Union[AnyModel, str]]) -> Optional[AnyModel]:
        if isinstance(v, str):
            return OpenAIChatModel(type="chat", name=v, format="openai")
        return v

    @validator("replicas")
    def convert_replicas(cls, v: Range[int]) -> Range[int]:
        if v.max is None:
            raise ValueError("The maximum number of replicas is required")
        if v.min is None:
            v.min = 0
        if v.min < 0:
            raise ValueError("The minimum number of replicas must be greater than or equal to 0")
        return v

    @validator("gateway")
    def validate_gateway(
        cls, v: Optional[Union[bool, str]]
    ) -> Optional[Union[Literal[False], str]]:
        if v == True:
            raise ValueError(
                "The `gateway` property must be a string or boolean `false`, not boolean `true`"
            )
        return v

    @root_validator()
    def validate_scaling(cls, values):
        scaling = values.get("scaling")
        replicas = values.get("replicas")
        if replicas and replicas.min != replicas.max and not scaling:
            raise ValueError("When you set `replicas` to a range, ensure to specify `scaling`.")
        if replicas and replicas.min == replicas.max and scaling:
            raise ValueError("To use `scaling`, `replicas` must be set to a range.")
        return values

    @validator("rate_limits")
    def validate_rate_limits(cls, v: list[RateLimit]) -> list[RateLimit]:
        counts = Counter(limit.prefix for limit in v)
        duplicates = [prefix for prefix, count in counts.items() if count > 1]
        if duplicates:
            raise ValueError(
                f"Prefixes {duplicates} are used more than once."
                " Each rate limit should have a unique path prefix"
            )
        return v

    @validator("probes")
    def validate_probes(cls, v: list[ProbeConfig]) -> list[ProbeConfig]:
        if has_duplicates(v):
            # Using a custom validator instead of Field(unique_items=True) to avoid Pydantic bug:
            # https://github.com/pydantic/pydantic/issues/3765
            # Because of the bug, our gen_schema_reference.py fails to determine the type of
            # ServiceConfiguration.probes and insert the correct hyperlink.
            raise ValueError("Probes must be unique")
        return v


class ServiceConfiguration(
    ProfileParams,
    BaseRunConfiguration,
    ConfigurationWithCommandsParams,
    ServiceConfigurationParams,
):
    type: Literal["service"] = "service"

    class Config(
        ProfileParams.Config,
        BaseRunConfiguration.Config,
        ServiceConfigurationParams.Config,
    ):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            ProfileParams.Config.schema_extra(schema)
            BaseRunConfiguration.Config.schema_extra(schema)
            ServiceConfigurationParams.Config.schema_extra(schema)


AnyRunConfiguration = Union[DevEnvironmentConfiguration, TaskConfiguration, ServiceConfiguration]


class RunConfiguration(CoreModel):
    __root__: Annotated[
        AnyRunConfiguration,
        Field(discriminator="type"),
    ]


def parse_run_configuration(data: dict) -> AnyRunConfiguration:
    try:
        conf = RunConfiguration.parse_obj(data).__root__
    except ValidationError as e:
        raise ConfigurationError(e)
    return conf


class ApplyConfigurationType(str, Enum):
    DEV_ENVIRONMENT = "dev-environment"
    TASK = "task"
    SERVICE = "service"
    FLEET = "fleet"
    GATEWAY = "gateway"
    VOLUME = "volume"


AnyApplyConfiguration = Union[
    AnyRunConfiguration,
    FleetConfiguration,
    GatewayConfiguration,
    VolumeConfiguration,
]


class ApplyConfiguration(CoreModel):
    __root__: Annotated[
        AnyApplyConfiguration,
        Field(discriminator="type"),
    ]


def parse_apply_configuration(data: dict) -> AnyApplyConfiguration:
    try:
        conf = ApplyConfiguration.parse_obj(data).__root__
    except ValidationError as e:
        raise ConfigurationError(e)
    return conf


AnyDstackConfiguration = AnyApplyConfiguration


class DstackConfiguration(CoreModel):
    __root__: Annotated[
        AnyDstackConfiguration,
        Field(discriminator="type"),
    ]

    class Config(CoreModel.Config):
        json_loads = orjson.loads
        json_dumps = pydantic_orjson_dumps_with_indent

        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            schema["$schema"] = "http://json-schema.org/draft-07/schema#"
            # Allow additionalProperties so that vscode and others not supporting
            # top-level oneOf do not warn about properties being invalid.
            schema["additionalProperties"] = True
