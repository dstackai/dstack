import re
import string
from collections import Counter
from enum import Enum
from pathlib import PurePosixPath
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    RootModel,
    Tag,
    ValidationError,
    ValidationInfo,
    conint,
    constr,
    field_validator,
    model_validator,
)
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Self

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import (
    JSON_SCHEMA_DIALECT,
    CoreModel,
    EntityReference,
    RegistryAuth,
    validate_extra_ignore,
)
from dstack._internal.core.models.duration import Duration, parse_off_duration
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.files import FilePathMapping
from dstack._internal.core.models.fleets import FleetConfiguration
from dstack._internal.core.models.gateways import GatewayConfiguration
from dstack._internal.core.models.presets import PresetConfiguration
from dstack._internal.core.models.profiles import (
    ProfileParams,
    SpotPolicy,
)
from dstack._internal.core.models.resources import Range, ResourcesSpec
from dstack._internal.core.models.routers import ReplicaGroupRouterConfig
from dstack._internal.core.models.services import AnyModel, OpenAIChatModel
from dstack._internal.core.models.unix import UnixUser
from dstack._internal.core.models.volumes import (
    AnyVolumeConfiguration,
    BaseVolumeConfiguration,
    MountPoint,
    VolumeConfiguration,
    parse_mount_point,
    parse_volume_configuration,
)
from dstack._internal.core.services import is_valid_replica_group_name
from dstack._internal.proxy.gateway.const import SERVICE_SCALING_WINDOWS
from dstack._internal.utils.common import has_duplicates, list_enum_values_for_annotation

CommandsList = List[str]
ValidPort = conint(gt=0, le=65535)
MAX_INT64 = 2**63 - 1
SERVICE_HTTPS_DEFAULT = True
STRIP_PREFIX_DEFAULT = True
RUN_PRIOTIRY_MIN = 0
RUN_PRIOTIRY_MAX = 100
RUN_PRIORITY_DEFAULT = 0
LEGACY_REPO_DIR = "/workflow"
MIN_PROBE_TIMEOUT = 1
MIN_PROBE_INTERVAL = 1
DEFAULT_PROBE_URL = "/"
DEFAULT_PROBE_TIMEOUT = 10
DEFAULT_PROBE_INTERVAL = 15
DEFAULT_PROBE_READY_AFTER = 1
DEFAULT_PROBE_METHOD = "get"
DEFAULT_PROBE_UNTIL_READY = False
MAX_PROBE_URL_LEN = 2048
DEFAULT_REPLICA_GROUP_NAME = "0"
OPENAI_MODEL_PROBE_TIMEOUT = 30
ALLOWED_SCALING_WINDOWS_DESCRIPTION = ", ".join(f"`{w}s`" for w in SERVICE_SCALING_WINDOWS)
DEFAULT_SCALING_WINDOW = 60
assert DEFAULT_SCALING_WINDOW in SERVICE_SCALING_WINDOWS


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
    PY314 = "3.14"


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


class RepoExistsAction(str, Enum):
    ERROR = "error"
    """`ERROR` means do not try to check out and terminate the run with an error. This is the default action since 0.20.0."""
    SKIP = "skip"
    """`SKIP` means do not try to check out and skip the repo. This is the logic hardcoded in the pre-0.20.0 runner."""


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
    path: Annotated[
        str,
        Field(
            description=(
                "The repo path inside the run container. Relative paths are resolved"
                " relative to the working directory"
            )
        ),
    ] = "."
    if_exists: Annotated[
        RepoExistsAction,
        Field(
            description=(
                "The action to be taken if `path` exists and is not empty."
                f" One of: {list_enum_values_for_annotation(RepoExistsAction)}"
            ),
        ),
    ] = RepoExistsAction.ERROR

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        model_schema = handler(source_type)
        return core_schema.no_info_before_validator_function(
            cls._parse_shorthand,
            model_schema,
            json_schema_input_schema=core_schema.union_schema(
                [model_schema, core_schema.str_schema()]
            ),
        )

    @classmethod
    def _parse_shorthand(cls, v: Any) -> Any:
        if isinstance(v, str):
            return cls.parse(v)
        return v

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

    @model_validator(mode="after")
    def validate_local_path_or_url(self) -> Self:
        if self.local_path and self.url:
            raise ValueError("`local_path` and `url` are mutually exclusive")
        if not self.local_path and not self.url:
            raise ValueError("Either `local_path` or `url` must be specified")
        return self

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v.startswith("~") and PurePosixPath(v).parts[0] != "~":
            raise ValueError("`~username` syntax is not supported")
        return v


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
    window: Annotated[
        Optional[Duration],
        Field(
            description=(
                "The time window used to calculate requests per second."
                f" Allowed values: {ALLOWED_SCALING_WINDOWS_DESCRIPTION}."
                f" Defaults to `{DEFAULT_SCALING_WINDOW}s`"
            ),
        ),
    ] = None
    scale_up_delay: Annotated[
        Duration,
        Field(
            description=(
                "The minimum time, in seconds, between a scaling event and the next scale-up decision."
                " Used to prevent overly frequent scaling"
            )
        ),
    ] = Duration.parse("5m")
    scale_down_delay: Annotated[
        Duration,
        Field(
            description=(
                "The minimum time, in seconds, between a scaling event and the next scale-down decision."
                " Used to prevent overly frequent scaling"
            )
        ),
    ] = Duration.parse("10m")

    @field_validator("window")
    @classmethod
    def validate_window(cls, v: Optional[Duration]) -> Optional[Duration]:
        if v is not None and v not in SERVICE_SCALING_WINDOWS:
            raise ValueError(f"Window must be one of: {ALLOWED_SCALING_WINDOWS_DESCRIPTION}")
        return v


class IPAddressPartitioningKey(CoreModel):
    type: Annotated[Literal["ip_address"], Field(description="Partitioning type")] = "ip_address"


class HeaderPartitioningKey(CoreModel):
    type: Annotated[Literal["header"], Field(description="Partitioning type")] = "header"
    header: Annotated[
        str,
        Field(
            description="Name of the header to use for partitioning",
            pattern=r"^[a-zA-Z0-9-_]+$",  # prevent Nginx config injection
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
            pattern=r"^/[^\s\\{}]*$",  # prevent Nginx config injection
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
    type: Annotated[
        Literal["http"],
        Field(description="The probe type. Must be `http`"),
    ]  # expect other probe types in the future, namely `exec`
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
        Field(description="A list of HTTP headers to include in the request", max_length=16),
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
        Optional[Duration],
        Field(
            description=(
                f"Maximum amount of time the HTTP request is allowed to take. Defaults to `{DEFAULT_PROBE_TIMEOUT}s`"
            )
        ),
    ] = None
    interval: Annotated[
        Optional[Duration],
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
    until_ready: Annotated[
        Optional[bool],
        Field(
            description=(
                "If `true`, the probe will stop being executed as soon as it reaches the"
                " `ready_after` threshold of successful executions."
                f" Defaults to `{str(DEFAULT_PROBE_UNTIL_READY).lower()}`"
            ),
        ),
    ] = None

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: Optional[Duration]) -> Optional[Duration]:
        if v is not None and v < MIN_PROBE_TIMEOUT:
            raise ValueError(f"Probe timeout cannot be shorter than {MIN_PROBE_TIMEOUT}s")
        return v

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: Optional[Duration]) -> Optional[Duration]:
        if v is not None and v < MIN_PROBE_INTERVAL:
            raise ValueError(f"Probe interval cannot be shorter than {MIN_PROBE_INTERVAL}s")
        return v

    @field_validator("url")
    @classmethod
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

    @model_validator(mode="after")
    def validate_body_matches_method(self) -> Self:
        method: HTTPMethod = self.method
        if self.body is not None and method in ["get", "head"]:
            raise ValueError(f"Cannot set request body for the `{method}` method")
        return self


def _parse_mount_point_shorthand(v: Union[MountPoint, str]) -> MountPoint:
    if isinstance(v, str):
        return parse_mount_point(v)
    return v


def _parse_port_shorthand(v: Union[int, str, PortMapping]) -> PortMapping:
    if isinstance(v, int):
        return PortMapping(local_port=v, container_port=v)
    if isinstance(v, str):
        return PortMapping.parse(v)
    return v


# `json_schema_input_type` keeps the shorthand visible in the generated JSON Schema, which used to
# be patched in per field by a sibling config class.
MountPointOrShorthand = Annotated[
    MountPoint,
    BeforeValidator(_parse_mount_point_shorthand, json_schema_input_type=Union[MountPoint, str]),
]
# Declared as `PortMapping` rather than the input union: that is what the value always is once
# `_parse_port_shorthand` has run.
PortMappingOrShorthand = Annotated[
    PortMapping,
    BeforeValidator(
        _parse_port_shorthand,
        json_schema_input_type=Union[
            ValidPort, constr(pattern=r"^(?:[0-9]+|\*):[0-9]+$"), PortMapping
        ],
    ),
]


class BaseRunConfiguration(CoreModel):
    type: Literal["none"]
    name: Annotated[
        Optional[str],
        Field(description="The run name. If not specified, a random name is generated"),
    ] = None
    image: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of the Docker image to run."
                " If no `image` is specified, `dstack` uses an Ubuntu 24.04-based Docker image that comes pre-configured"
                " with `uv`, `python`, `pip`, the CUDA 13.0 runtime, InfiniBand, NCCL, and NCCL tests."
                " It may also include provider-specific components such as EFA support on AWS."
                " For non-Nvidia accelerators or NVidia GPUs unsupported by CUDA 13.0 (e.g. V100, P100), specify a custom Docker image."
            )
        ),
    ] = None
    user: Annotated[
        Optional[str],
        Field(
            description=(
                "The user inside the container, `user_name_or_id[:group_name_or_id]`"
                " (e.g., `ubuntu`, `1000:1000`). Defaults to the default user from the `image`"
            )
        ),
    ] = None
    privileged: Annotated[bool, Field(description="Run the container in privileged mode")] = False
    entrypoint: Annotated[Optional[str], Field(description="The Docker entrypoint")] = None
    working_dir: Annotated[
        Optional[str],
        Field(
            description=(
                "The absolute path to the working directory inside the container."
                " Defaults to the `image`'s default working directory"
            ),
        ),
    ] = None
    home_dir: str = "/root"
    """`home_dir` is deprecated since 0.18.31 and has no effect."""
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
    volumes: Annotated[
        List[MountPointOrShorthand], Field(description="The volumes mount points")
    ] = []
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
    dstack: Annotated[
        bool,
        Field(
            description=(
                "Make the dstack server accessible inside the run. "
                "No authentication credentials are provided"
            )
        ),
    ] = False
    setup: CommandsList = []
    """
    setup: Deprecated since 0.18.31. It has no effect for tasks and services; for
    dev environments it runs right before `init`.
    """

    @field_validator("python", mode="before")
    @classmethod
    def convert_python(cls, v, info: ValidationInfo) -> Optional[PythonVersion]:
        if v is not None and info.data.get("image"):
            raise ValueError("`image` and `python` are mutually exclusive fields")
        if isinstance(v, float):
            v = str(v)
            if v == "3.1":
                v = "3.10"
        if isinstance(v, str):
            return PythonVersion(v)
        return v

    @field_validator("docker", mode="before")
    @classmethod
    def _docker(cls, v, info: ValidationInfo) -> Optional[bool]:
        if v is True and info.data.get("image"):
            raise ValueError("`image` and `docker` are mutually exclusive fields")
        if v is True and info.data.get("python"):
            raise ValueError("`python` and `docker` are mutually exclusive fields")
        if v is True and info.data.get("nvcc"):
            raise ValueError("`nvcc` and `docker` are mutually exclusive fields")
        # Ideally, we'd like to also prohibit privileged=False when docker=True,
        #   but it's not possible to do so without breaking backwards compatibility.
        return v

    @field_validator("repos")
    @classmethod
    def validate_repos(cls, v) -> RepoSpec:
        if len(v) > 1:
            raise ValueError("A maximum of one repo is currently supported")
        return v

    @field_validator("user")
    @classmethod
    def validate_user(cls, v) -> Optional[str]:
        if v is None:
            return None
        UnixUser.parse(v)
        return v

    @field_validator("shell")
    @classmethod
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
        List[PortMappingOrShorthand],
        Field(description="Port numbers/mapping to expose"),
    ] = []


class ConfigurationWithCommandsParams(CoreModel):
    commands: Annotated[CommandsList, Field(description="The shell commands to run")] = []

    @model_validator(mode="after")
    def check_image_or_commands_present(self) -> Self:
        # If replicas is list, skip validation - commands come from replica groups
        replicas = getattr(self, "replicas", None)
        if isinstance(replicas, list):
            return self
        # If groups is set, skip validation - commands come from node groups
        if getattr(self, "groups", None) is not None:
            return self

        if not self.commands and not getattr(self, "image", None):
            raise ValueError("Either `commands` or `image` must be set")
        return self


class DevEnvironmentConfigurationParams(CoreModel):
    ide: Annotated[
        Optional[Union[Literal["vscode"], Literal["cursor"], Literal["windsurf"], Literal["zed"]]],
        Field(
            description="The IDE to pre-install. Supported values include `vscode`, `cursor`, `windsurf`, and `zed`. Defaults to no IDE (SSH only)"
        ),
    ] = None
    version: Annotated[
        Optional[str],
        Field(
            description="The version of the IDE. For `windsurf`, the version is in the format `version@commit`"
        ),
    ] = None
    init: Annotated[CommandsList, Field(description="The shell commands to run on startup")] = []
    inactivity_duration: Annotated[
        Optional[int],
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

    # Not `OptionalOffableDuration`: "off" collapses to `None` here rather than staying as the string.
    @field_validator(
        "inactivity_duration",
        mode="before",
        json_schema_input_type=Optional[Union[Literal["off"], int, bool, str]],
    )
    @classmethod
    def parse_inactivity_duration(
        cls, v: Optional[Union[Literal["off"], int, bool, str]]
    ) -> Optional[int]:
        v = parse_off_duration(v)
        if isinstance(v, int):
            return v
        return None

    @model_validator(mode="after")
    def validate_ide_and_version(self) -> Self:
        ide = self.ide
        version = self.version
        if version and ide is None:
            raise ValueError("`version` requires `ide` to be set")
        if ide == "windsurf" and version:
            # Validate format: version@commit
            if not re.match(r"^.+@[a-f0-9]+$", version):
                raise ValueError(
                    f"Invalid Windsurf version format: `{version}`. "
                    "Expected format: `version@commit` (e.g., `1.106.0@8951cd3ad688e789573d7f51750d67ae4a0bea7d`)"
                )
        return self


class DevEnvironmentConfiguration(
    ProfileParams,
    BaseRunConfiguration,
    ConfigurationWithPortsParams,
    DevEnvironmentConfigurationParams,
):
    type: Literal["dev-environment"] = "dev-environment"

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            raise ValueError("entrypoint is not supported for dev-environment")
        return v

    @model_validator(mode="after")
    def validate_dstack_and_inactivity_duration(self) -> Self:
        if self.dstack and self.inactivity_duration is not None:
            # The persistent server connection counts as activity, so inactivity is never detected
            raise ValueError("`dstack` is not supported together with `inactivity_duration`")
        return self


class NodeGroup(CoreModel):
    name: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of the node group. If not provided, defaults to '0', '1', etc. "
                "based on position."
            )
        ),
    ] = None
    nodes: Annotated[int, Field(description="The number of nodes in this group", ge=1)] = 1
    resources: Annotated[
        ResourcesSpec,
        Field(
            description=(
                "The resources requirements for nodes in this group. "
                "Does not inherit top-level `resources` (same as replica groups)"
            )
        ),
    ] = ResourcesSpec()
    commands: Annotated[
        CommandsList,
        Field(description="The shell commands to run for nodes in this group"),
    ] = []
    ports: Annotated[
        List[PortMappingOrShorthand],
        Field(description="Port numbers/mapping to expose for nodes in this group"),
    ] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not is_valid_replica_group_name(v):
                raise ValueError("Node group name should match regex '^[a-z0-9][a-z0-9-]{0,39}$'")
        return v

    @property
    def required_name(self) -> str:
        """Name after normalization.

        Omitted names are filled by TaskConfiguration.validate_groups; directly
        constructed groups must set `name` explicitly.
        """
        if self.name is None:
            raise ValueError("NodeGroup.name must be set before use")
        return self.name


class TaskConfigurationParams(CoreModel):
    nodes: Annotated[
        Optional[int],
        Field(description="The number of nodes for homogeneous multi-node tasks", ge=1),
    ] = None
    groups: Annotated[
        Optional[List[NodeGroup]],
        Field(
            description=(
                "A list of node groups for heterogeneous multi-node tasks. "
                "Mutually exclusive with `nodes`. "
                "When `groups` is set, top-level `commands`, `ports`, and `entrypoint` are "
                "not allowed; specify `commands` and `ports` in each node group instead. "
                "Top-level `resources` is not rejected (same as replica groups; see server "
                "defaults), but each group's `resources` is used for provisioning — omit "
                "means default empty resources, not inheritance from the top level."
            ),
        ),
    ] = None

    @model_validator(mode="before")
    @classmethod
    def validate_nodes_xor_groups(cls, data):
        if not isinstance(data, dict):
            return data
        if data.get("groups") is not None and data.get("nodes") is not None:
            raise ValueError("`nodes` and `groups` are mutually exclusive")
        return data

    @field_validator("groups")
    @classmethod
    def validate_groups(cls, v: Optional[List[NodeGroup]]) -> Optional[List[NodeGroup]]:
        if v is None:
            return v
        if not v:
            raise ValueError("`groups` cannot be an empty list")
        for index, group in enumerate(v):
            if group.name is None:
                group.name = str(index)
        counts = Counter(group.name for group in v)
        duplicates = [name for name, count in counts.items() if count > 1]
        if duplicates:
            raise ValueError(
                f"Duplicate node group names found: {duplicates}. "
                "Each node group must have a unique name."
            )
        return v


class TaskConfiguration(
    ProfileParams,
    BaseRunConfiguration,
    ConfigurationWithCommandsParams,
    ConfigurationWithPortsParams,
    TaskConfigurationParams,
):
    type: Literal["task"] = "task"

    @model_validator(mode="after")
    def validate_top_level_properties_with_node_groups(self) -> Self:
        """When groups is set, forbid top-level commands, ports, and entrypoint.

        Top-level `resources` is not rejected: the server may mutate it later
        (defaults/plugins), and strict parse-time checks would break round-trips.
        Provisioning still uses each group's `resources` (default ResourcesSpec()),
        not top-level — same as replica groups.
        """
        if self.groups is None:
            return self
        if self.commands:
            raise ValueError(
                "Top-level `commands` is not allowed when `groups` is set. "
                "Specify `commands` in each node group instead."
            )
        if self.ports:
            raise ValueError(
                "Top-level `ports` is not allowed when `groups` is set. "
                "Specify `ports` in each node group instead."
            )
        if self.entrypoint is not None:
            raise ValueError(
                "Top-level `entrypoint` is not allowed when `groups` is set. "
                "Specify `commands` in each node group instead."
            )
        return self

    @model_validator(mode="after")
    def validate_node_groups_have_commands_or_image(self) -> Self:
        """When groups is set, each group needs commands or a task-level image."""
        if self.groups is None:
            return self
        task_has_image = self.image is not None
        for group in self.groups:
            if not group.commands and not task_has_image:
                raise ValueError(
                    f"Node group '{group.name}': either `commands` must be set in the group, "
                    "or `image` at the task level."
                )
        return self

    @property
    def node_groups(self) -> List[NodeGroup]:
        if self.groups is not None:
            return self.groups
        return [
            NodeGroup(
                name=DEFAULT_REPLICA_GROUP_NAME,
                # Omitted nodes means a 1-node task (self.nodes stays None for serialization).
                nodes=self.nodes if self.nodes is not None else 1,
                commands=self.commands,
                resources=self.resources,
                ports=self.ports,
            )
        ]

    @property
    def nodes_num(self) -> int:
        return sum(group.nodes for group in self.node_groups)


def _validate_replica_range(v: Range[int]) -> Range[int]:
    """Validate a Range[int] used for replica counts."""
    if v.max is None:
        raise ValueError("The maximum number of replicas is required")
    if v.min is None:
        v.min = 0
    if v.min < 0:
        raise ValueError("The minimum number of replicas must be greater than or equal to 0")
    return v


class ReplicaGroup(CoreModel):
    name: Annotated[
        Optional[str],
        Field(
            description="The name of the replica group. If not provided, defaults to '0', '1', etc. based on position."
        ),
    ] = None
    count: Annotated[
        Range[int],
        Field(
            description="The number of replicas. Can be a number (e.g. `2`) or a range (`0..4` or `1..8`). "
            "If it's a range, the `scaling` property is required"
        ),
    ]
    scaling: Annotated[
        Optional[ScalingSpec],
        Field(description="The auto-scaling rules. Required if `count` is set to a range"),
    ] = None

    resources: Annotated[
        ResourcesSpec,
        Field(description="The resources requirements for replicas in this group"),
    ] = ResourcesSpec()
    spot_policy: Annotated[
        Optional[SpotPolicy],
        Field(
            description=(
                "The policy for provisioning spot or on-demand instances for replicas in this group:"
                f" {list_enum_values_for_annotation(SpotPolicy)}"
            )
        ),
    ] = None
    reservation: Annotated[
        Optional[str],
        Field(
            description=(
                "The existing reservation to use for replicas in this group."
                " Supports AWS Capacity Reservations, AWS Capacity Blocks, and GCP reservations"
            )
        ),
    ] = None

    commands: Annotated[
        CommandsList,
        Field(description="The shell commands to run for replicas in this group"),
    ] = []
    image: Annotated[
        Optional[str],
        Field(
            description="The name of the Docker image to run for replicas in this group. "
            "Mutually exclusive with group-level `docker` and `python`."
        ),
    ] = None
    python: Annotated[
        Optional[PythonVersion],
        Field(
            description="The major version of Python for replicas in this group. "
            "Mutually exclusive with group-level `image` and `docker`."
        ),
    ] = None
    nvcc: Annotated[
        Optional[bool],
        Field(
            description="Use the image with NVIDIA CUDA Compiler (NVCC) included for replicas in this group. "
            "Mutually exclusive with group-level `docker`."
        ),
    ] = None
    docker: Annotated[
        Optional[bool],
        Field(
            description="Use the docker-in-docker image for this group "
            "(injects `start-dockerd` and runs privileged). Mutually "
            "exclusive with group-level `image`, `python`, and `nvcc`."
        ),
    ] = None
    privileged: Annotated[
        Optional[bool],
        Field(description="Run replicas in this group in privileged mode."),
    ] = None
    router: Annotated[
        Optional[ReplicaGroupRouterConfig],
        Field(
            description="When set, replicas in this group run the in-service HTTP router (e.g. SGLang).",
        ),
    ] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not is_valid_replica_group_name(v):
                raise ValueError("Resource name should match regex '^[a-z0-9][a-z0-9-]{0,39}$'")
        return v

    @field_validator("count")
    @classmethod
    def convert_count(cls, v: Range[int]) -> Range[int]:
        return _validate_replica_range(v)

    @field_validator("python", mode="before")
    @classmethod
    def convert_python(cls, v, info: ValidationInfo) -> Optional[PythonVersion]:
        if v is not None and info.data.get("image"):
            raise ValueError("`image` and `python` are mutually exclusive within a replica group")
        if isinstance(v, float):
            v = str(v)
            if v == "3.1":
                v = "3.10"
        if isinstance(v, str):
            return PythonVersion(v)
        return v

    @field_validator("docker", mode="before")
    @classmethod
    def _docker(cls, v, info: ValidationInfo) -> Optional[bool]:
        if v is True and info.data.get("image"):
            raise ValueError("`image` and `docker` are mutually exclusive within a replica group")
        if v is True and info.data.get("python"):
            raise ValueError("`python` and `docker` are mutually exclusive within a replica group")
        if v is True and info.data.get("nvcc"):
            raise ValueError("`nvcc` and `docker` are mutually exclusive within a replica group")
        return v

    @field_validator("privileged", mode="before")
    @classmethod
    def _privileged(cls, v, info: ValidationInfo) -> Optional[bool]:
        # Docker-in-docker requires privileged mode. The service level
        # cannot enforce this rule because its `privileged` field defaults
        # to `False` (existing backwards-compatibility constraint), so it
        # cannot distinguish "unset" from explicit `False`. At the group
        # level we keep `privileged` as `Optional[bool] = None`, so we can.
        if v is False and info.data.get("docker") is True:
            raise ValueError(
                "`privileged: false` is incompatible with `docker: true` within "
                "a replica group (docker-in-docker requires privileged mode)"
            )
        return v

    @model_validator(mode="after")
    def validate_scaling(self) -> Self:
        scaling = self.scaling
        count = self.count
        if count and count.min != count.max and not scaling:
            raise ValueError("When you set `count` to a range, ensure to specify `scaling`.")
        if count and count.min == count.max and scaling:
            raise ValueError("To use `scaling`, `count` must be set to a range.")
        return self


class ServiceConfigurationParams(CoreModel):
    port: Annotated[
        # NOTE: it's a PortMapping for historical reasons. Only `port.container_port` is used.
        Union[ValidPort, constr(pattern=r"^[0-9]+:[0-9]+$"), PortMapping],
        Field(description="The port the application listens on"),
    ]
    gateway: Annotated[
        Optional[
            Union[
                bool,
                EntityReference,
                str,  # For server response compatibility with pre-0.20.20 clients
            ]
        ],
        Field(
            union_mode="left_to_right",  # preserving pydantic v1 parsing behavior
            description=(
                "The name of the gateway. Specify boolean `false` to run without a gateway."
                " Specify boolean `true` to run with the default gateway."
                " Omit to run with the default gateway if there is one, or without a gateway otherwise"
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
    # A discriminator cannot read `format` off the documented `model: <name>` shorthand, so it
    # would reject it. This works only because the `convert_model` pre-validator below expands a
    # bare string into an `OpenAIChatModel` first — leaving the union something that carries
    # `format` either way: an attribute on the expanded model, or a key in a user-supplied mapping.
    model: Annotated[
        Optional[AnyModel],
        Field(
            discriminator="format",
            description=(
                "Mapping of the model for the OpenAI-compatible endpoint provided by `dstack`."
                " Can be a full model format definition or just a model name."
                " If it's a name, the service is expected to expose an OpenAI-compatible"
                " API at the `/v1` path"
            ),
        ),
    ] = None
    https: Annotated[
        Optional[Union[bool, Literal["auto"]]],
        Field(
            description="Enable HTTPS if running with a gateway."
            " Set to `auto` to determine automatically based on gateway configuration."
            f" Defaults to `{str(SERVICE_HTTPS_DEFAULT).lower()}`"
        ),
    ] = None
    auth: Annotated[bool, Field(description="Enable the authorization")] = True

    scaling: Annotated[
        Optional[ScalingSpec],
        Field(description="The auto-scaling rules. Required if `replicas` is set to a range"),
    ] = None
    rate_limits: Annotated[list[RateLimit], Field(description="Rate limiting rules")] = []
    probes: Annotated[
        Optional[list[ProbeConfig]],
        Field(
            description="The list of probes to determine service health. "
            "If `model` is set, defaults to a `/v1/chat/completions` probe. "
            "Set explicitly to override"
        ),
    ] = None  # None = omitted (may get default when model is set); [] = explicit empty

    replicas: Annotated[
        Optional[
            # `Tag` only names the arm in validation errors. Without it the `loc` of a bad
            # `replicas` spells out the whole wrapped schema —
            # `service.replicas.list[function-after[validate_scaling(), ReplicaGroup]].0` — which
            # is what `dstack apply` shows the user.
            Union[
                Annotated[list[ReplicaGroup], Tag("ReplicaGroup")],
                Annotated[Range[int], Tag("Range[int]")],
            ]
        ],
        Field(
            description=(
                "The number of replicas or a list of replica groups. "
                "Can be an integer (e.g., `2`), a range (e.g., `0..4`), or a list of replica groups. "
                "Each replica group defines replicas with shared configuration "
                "(commands, resources, scaling). "
                "When `replicas` is a list of replica groups, top-level `scaling`, `commands`, "
                "and `resources` are not allowed and must be specified in each replica group instead. "
            )
        ),
    ] = None

    @field_validator("port")
    @classmethod
    def convert_port(cls, v) -> PortMapping:
        if isinstance(v, int):
            return PortMapping(local_port=80, container_port=v)
        elif isinstance(v, str):
            return PortMapping.parse(v)
        return v

    @field_validator("model", mode="before", json_schema_input_type=Optional[Union[AnyModel, str]])
    @classmethod
    def convert_model(cls, v: Optional[Union[AnyModel, str]]) -> Optional[AnyModel]:
        if isinstance(v, str):
            return OpenAIChatModel(type="chat", name=v, format="openai")
        return v

    @field_validator("rate_limits")
    @classmethod
    def validate_rate_limits(cls, v: list[RateLimit]) -> list[RateLimit]:
        counts = Counter(limit.prefix for limit in v)
        duplicates = [prefix for prefix, count in counts.items() if count > 1]
        if duplicates:
            raise ValueError(
                f"Prefixes {duplicates} are used more than once."
                " Each rate limit should have a unique path prefix"
            )
        return v

    @field_validator("probes")
    @classmethod
    def validate_probes(cls, v: Optional[list[ProbeConfig]]) -> Optional[list[ProbeConfig]]:
        if v is None:
            return v
        if has_duplicates(v):
            # Using a custom validator instead of Field(unique_items=True) to avoid Pydantic bug:
            # https://github.com/pydantic/pydantic/issues/3765
            # Because of the bug, our gen_schema_reference.py fails to determine the type of
            # ServiceConfiguration.probes and insert the correct hyperlink.
            raise ValueError("Probes must be unique")
        return v

    @field_validator("gateway")
    @classmethod
    def validate_gateway(
        cls, v: Optional[Union[bool, EntityReference, str]]
    ) -> Optional[Union[bool, EntityReference]]:
        if isinstance(v, str):
            return EntityReference.parse(v)
        return v

    @field_validator("replicas")
    @classmethod
    def validate_replicas(
        cls, v: Optional[Union[Range[int], List[ReplicaGroup]]]
    ) -> Optional[Union[Range[int], List[ReplicaGroup]]]:
        if v is None:
            return v
        if isinstance(v, Range):
            return _validate_replica_range(v)

        if isinstance(v, list):
            if not v:
                raise ValueError("`replicas` cannot be an empty list")

            # Assign default names to groups without names
            for index, group in enumerate(v):
                if group.name is None:
                    group.name = str(index)

            # Check for duplicate names
            names = [group.name for group in v]
            if len(names) != len(set(names)):
                duplicates = [name for name in set(names) if names.count(name) > 1]
                raise ValueError(
                    f"Duplicate replica group names found: {duplicates}. "
                    "Each replica group must have a unique name."
                )
        return v

    @model_validator(mode="after")
    def validate_scaling(self) -> Self:
        scaling = self.scaling
        replicas = self.replicas

        if isinstance(replicas, Range):
            if replicas and replicas.min != replicas.max and not scaling:
                raise ValueError(
                    "When you set `replicas` to a range, ensure to specify `scaling`."
                )
            if replicas and replicas.min == replicas.max and scaling:
                raise ValueError("To use `scaling`, `replicas` must be set to a range.")
        return self

    @model_validator(mode="after")
    def validate_top_level_properties_with_replica_groups(self) -> Self:
        """
        When replicas is a list of ReplicaGroup, forbid top-level scaling and commands.
        """
        replicas = self.replicas

        if not isinstance(replicas, list):
            return self

        scaling = self.scaling
        if scaling is not None:
            raise ValueError(
                "Top-level `scaling` is not allowed when `replicas` is a list. "
                "Specify `scaling` in each replica group instead."
            )

        commands = getattr(self, "commands", None)
        if commands:
            raise ValueError(
                "Top-level `commands` is not allowed when `replicas` is a list. "
                "Specify `commands` in each replica group instead."
            )

        return self

    @model_validator(mode="after")
    def validate_no_mixed_service_and_group_container_fields(self) -> Self:
        """
        When replicas is a list, certain fields may be set
        at the service level OR in replica groups, never both. Mixing is
        rejected — including partial mixing, where only some groups set a
        field the service also sets — because it leaves precedence ambiguous.
        """
        replicas = self.replicas
        if not isinstance(replicas, list):
            return self

        checks = [
            (
                "image",
                getattr(self, "image", None) is not None,
                lambda g: g.image is not None,
            ),
            (
                "docker",
                getattr(self, "docker", None) is True,
                lambda g: g.docker is not None,
            ),
            (
                "privileged",
                getattr(self, "privileged", None) is True,
                lambda g: g.privileged is not None,
            ),
            (
                "python",
                getattr(self, "python", None) is not None,
                lambda g: g.python is not None,
            ),
            (
                "nvcc",
                getattr(self, "nvcc", None) is True,
                lambda g: g.nvcc is not None,
            ),
            (
                "spot_policy",
                getattr(self, "spot_policy", None) is not None,
                lambda g: g.spot_policy is not None,
            ),
            (
                "reservation",
                getattr(self, "reservation", None) is not None,
                lambda g: g.reservation is not None,
            ),
        ]

        for field, service_set, group_set in checks:
            if service_set:
                conflicting = [g.name for g in replicas if group_set(g)]
                if conflicting:
                    raise ValueError(
                        f"`{field}` is set at both the service level and in "
                        f"replica group(s) {conflicting}. Set `{field}` in one "
                        f"place only — either at the service level (all groups "
                        f"inherit) or per group, but not both."
                    )
        return self

    @model_validator(mode="after")
    def validate_no_conflicting_image_sources_across_levels(self) -> Self:
        """
        Image-source fields (`image`, `docker`, `python`, `nvcc`) cannot
        be mixed across service and group levels in conflicting ways.
        """
        replicas = self.replicas
        if not isinstance(replicas, list):
            return self

        forbidden = [
            (
                "image",
                getattr(self, "image", None) is not None,
                "docker",
                lambda g: g.docker is not None,
            ),
            (
                "image",
                getattr(self, "image", None) is not None,
                "python",
                lambda g: g.python is not None,
            ),
            (
                "image",
                getattr(self, "image", None) is not None,
                "nvcc",
                lambda g: g.nvcc is not None,
            ),
            (
                "docker",
                getattr(self, "docker", None) is True,
                "image",
                lambda g: g.image is not None,
            ),
            (
                "docker",
                getattr(self, "docker", None) is True,
                "python",
                lambda g: g.python is not None,
            ),
            (
                "docker",
                getattr(self, "docker", None) is True,
                "nvcc",
                lambda g: g.nvcc is not None,
            ),
            (
                "python",
                getattr(self, "python", None) is not None,
                "image",
                lambda g: g.image is not None,
            ),
            (
                "python",
                getattr(self, "python", None) is not None,
                "docker",
                lambda g: g.docker is not None,
            ),
            ("nvcc", getattr(self, "nvcc", None) is True, "image", lambda g: g.image is not None),
            (
                "nvcc",
                getattr(self, "nvcc", None) is True,
                "docker",
                lambda g: g.docker is not None,
            ),
        ]

        for s_field, s_set, g_field, g_pred in forbidden:
            if s_set:
                conflicting = [g.name for g in replicas if g_pred(g)]
                if conflicting:
                    raise ValueError(
                        f"Service-level `{s_field}` conflicts with group-level "
                        f"`{g_field}` in replica group(s) {conflicting}. "
                        f"These image-source fields are mutually exclusive."
                    )
        return self

    @model_validator(mode="after")
    def validate_replica_groups_have_commands_or_image(self) -> Self:
        """
        When replicas is a list, ensure each ReplicaGroup has something
        to run. Mirrors the service-level rule: either explicit
        `commands` or an `image` (group-level or service-level) is
        required.
        """
        replicas = self.replicas

        if not isinstance(replicas, list):
            return self

        service_has_image = getattr(self, "image", None) is not None

        for group in replicas:
            if not group.commands and group.image is None and not service_has_image:
                raise ValueError(
                    f"Replica group '{group.name}': either `commands` or "
                    "`image` must be set in the group, or `image` at the "
                    "service level."
                )

        return self

    @model_validator(mode="after")
    def validate_at_most_one_router_replica_group(self) -> Self:
        replicas = self.replicas
        if not isinstance(replicas, list):
            return self
        router_groups = [g for g in replicas if g.router is not None]
        if len(router_groups) > 1:
            raise ValueError("At most one replica group may specify `router`.")
        if router_groups:
            router_group = router_groups[0]
            if router_group.count.min != 1 or router_group.count.max != 1:
                raise ValueError("For now replica group with `router` must have `count: 1`.")
        return self


class ServiceConfiguration(
    ProfileParams,
    BaseRunConfiguration,
    ConfigurationWithCommandsParams,
    ServiceConfigurationParams,
):
    type: Literal["service"] = "service"

    @property
    def replica_groups(self) -> List[ReplicaGroup]:
        if self.replicas is None:
            return [
                ReplicaGroup(
                    name=DEFAULT_REPLICA_GROUP_NAME,
                    count=Range[int](min=1, max=1),
                    commands=self.commands,
                    resources=self.resources,
                    scaling=self.scaling,
                )
            ]
        if isinstance(self.replicas, list):
            return self.replicas
        if isinstance(self.replicas, Range):
            return [
                ReplicaGroup(
                    name=DEFAULT_REPLICA_GROUP_NAME,
                    count=self.replicas,
                    commands=self.commands,
                    resources=self.resources,
                    scaling=self.scaling,
                )
            ]
        raise ValueError(
            f"Invalid replicas type: {type(self.replicas)}. Expected None, Range[int], or List[ReplicaGroup]"
        )


AnyRunConfiguration = Union[DevEnvironmentConfiguration, TaskConfiguration, ServiceConfiguration]


class RunConfiguration(RootModel[Annotated[AnyRunConfiguration, Field(discriminator="type")]]):
    pass


def parse_run_configuration(data: dict) -> AnyRunConfiguration:
    try:
        conf = RunConfiguration.model_validate(data).root
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
    PRESET = "preset"


AnyApplyConfiguration = Union[
    AnyRunConfiguration,
    FleetConfiguration,
    GatewayConfiguration,
    AnyVolumeConfiguration,
    PresetConfiguration,
]


_AnyBaseApplyConfiguration = Annotated[
    Union[
        # Final configurations
        AnyRunConfiguration,
        FleetConfiguration,
        GatewayConfiguration,
        PresetConfiguration,
        # Base configurations (further parsing required to get a concrete AnyApplyConfiguration)
        BaseVolumeConfiguration,
    ],
    Field(discriminator="type"),
]


class BaseApplyConfiguration(RootModel[_AnyBaseApplyConfiguration]):
    """
    `BaseApplyConfiguration` parses the configuration based on the `type` discriminator field,
    but further dispatching (reparsing) may be required if there is another discriminator field,
    e.g., `BaseVolumeConfiguration` should be parsed again to get a backend-specific configuration
    based on the `backend` discriminator field.

    Don't use this model directly, use `parse_apply_configuration()` instead.
    """


def parse_apply_configuration(data: dict) -> AnyApplyConfiguration:
    try:
        # First-pass parsing ignoring extra fields, to get the base (or final) configuration
        conf = validate_extra_ignore(BaseApplyConfiguration, data).root
        if not isinstance(conf, BaseVolumeConfiguration):
            # If it's a final configuration (currently, any configuration other than
            # BaseVolumeConfiguration), parse again rejecting extra fields
            # for validation purposes only and return the final configuration
            _ = BaseApplyConfiguration.model_validate(data).root
            return conf
    except ValidationError as e:
        raise ConfigurationError(e)
    # Otherwise, delegate further parsing to more specific parser
    return parse_volume_configuration(data)


AnyDstackConfiguration = Union[
    AnyRunConfiguration,
    FleetConfiguration,
    GatewayConfiguration,
    VolumeConfiguration,
    PresetConfiguration,
]


def _dstack_configuration_schema(schema: Dict[str, Any]) -> None:
    schema["$schema"] = JSON_SCHEMA_DIALECT
    # Allow additionalProperties so that vscode and others not supporting
    # top-level oneOf do not warn about properties being invalid.
    schema["additionalProperties"] = True


class DstackConfiguration(
    RootModel[Annotated[AnyDstackConfiguration, Field(discriminator="type")]]
):
    model_config = ConfigDict(json_schema_extra=_dstack_configuration_schema)
