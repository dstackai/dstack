from enum import Enum
from typing import Any, Dict, List, Optional, Union, overload

from pydantic import Field, root_validator, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel, Duration
from dstack._internal.utils.tags import tags_validator

DEFAULT_RETRY_DURATION = 3600

DEFAULT_RUN_TERMINATION_IDLE_TIME = 5 * 60  # 5 minutes
DEFAULT_FLEET_TERMINATION_IDLE_TIME = 72 * 60 * 60  # 3 days

DEFAULT_STOP_DURATION = 300


class SpotPolicy(str, Enum):
    SPOT = "spot"
    ONDEMAND = "on-demand"
    AUTO = "auto"


class CreationPolicy(str, Enum):
    REUSE = "reuse"
    REUSE_OR_CREATE = "reuse-or-create"


class TerminationPolicy(str, Enum):
    DONT_DESTROY = "dont-destroy"
    DESTROY_AFTER_IDLE = "destroy-after-idle"


@overload
def parse_duration(v: None) -> None: ...


@overload
def parse_duration(v: Union[int, str]) -> int: ...


def parse_duration(v: Optional[Union[int, str]]) -> Optional[int]:
    if v is None:
        return None
    return Duration.parse(v)


def parse_max_duration(v: Optional[Union[int, str, bool]]) -> Optional[Union[str, int]]:
    return parse_off_duration(v)


def parse_stop_duration(v: Optional[Union[int, str, bool]]) -> Optional[Union[str, int]]:
    return parse_off_duration(v)


def parse_off_duration(v: Optional[Union[int, str, bool]]) -> Optional[Union[str, int]]:
    if v == "off" or v is False:
        return "off"
    if v is True:
        return None
    return parse_duration(v)


def parse_idle_duration(v: Optional[Union[int, str, bool]]) -> Optional[Union[str, int, bool]]:
    if v is False:
        return -1
    if v is True:
        return None
    return parse_duration(v)


# Deprecated in favor of ProfileRetry().
# TODO: Remove when no longer referenced.
class ProfileRetryPolicy(CoreModel):
    retry: Annotated[bool, Field(description="Whether to retry the run on failure or not")] = False
    duration: Annotated[
        Optional[Union[int, str]],
        Field(description="The maximum period of retrying the run, e.g., `4h` or `1d`"),
    ] = None

    _validate_duration = validator("duration", pre=True, allow_reuse=True)(parse_duration)

    @root_validator
    def _validate_fields(cls, values):
        if values["retry"] and "duration" not in values:
            values["duration"] = DEFAULT_RETRY_DURATION
        if values.get("duration") is not None:
            values["retry"] = True
        return values


class RetryEvent(str, Enum):
    NO_CAPACITY = "no-capacity"
    INTERRUPTION = "interruption"
    ERROR = "error"


class ProfileRetry(CoreModel):
    on_events: Annotated[
        Optional[List[RetryEvent]],
        Field(
            description=(
                "The list of events that should be handled with retry."
                " Supported events are `no-capacity`, `interruption`, and `error`."
                " Omit to retry on all events"
            )
        ),
    ] = None
    duration: Annotated[
        Optional[Union[int, str]],
        Field(description="The maximum period of retrying the run, e.g., `4h` or `1d`"),
    ] = None

    _validate_duration = validator("duration", pre=True, allow_reuse=True)(parse_duration)

    @root_validator
    def _validate_fields(cls, values):
        on_events = values.get("on_events", None)
        if on_events is not None and len(values["on_events"]) == 0:
            raise ValueError("`on_events` cannot be empty")
        return values


class UtilizationPolicy(CoreModel):
    _min_time_window = "5m"

    min_gpu_utilization: Annotated[
        int,
        Field(
            description=(
                "Minimum required GPU utilization, percent."
                " If any GPU has utilization below specified value during the whole time window,"
                " the run is terminated"
            ),
            ge=0,
            le=100,
        ),
    ]
    time_window: Annotated[
        Union[int, str],
        Field(
            description=(
                "The time window of metric samples taking into account to measure utilization"
                f" (e.g., `30m`, `1h`). Minimum is `{_min_time_window}`"
            )
        ),
    ]

    @validator("time_window", pre=True)
    def validate_time_window(cls, v: Union[int, str]) -> int:
        v = parse_duration(v)
        if v < parse_duration(cls._min_time_window):
            raise ValueError(f"Minimum time_window is {cls._min_time_window}")
        return v


class ProfileParams(CoreModel):
    backends: Annotated[
        Optional[List[BackendType]],
        Field(description="The backends to consider for provisioning (e.g., `[aws, gcp]`)"),
    ] = None
    regions: Annotated[
        Optional[List[str]],
        Field(
            description="The regions to consider for provisioning (e.g., `[eu-west-1, us-west4, westeurope]`)"
        ),
    ] = None
    availability_zones: Annotated[
        Optional[List[str]],
        Field(
            description="The availability zones to consider for provisioning (e.g., `[eu-west-1a, us-west4-a]`)"
        ),
    ] = None
    instance_types: Annotated[
        Optional[List[str]],
        Field(
            description="The cloud-specific instance types to consider for provisioning (e.g., `[p3.8xlarge, n1-standard-4]`)"
        ),
    ] = None
    reservation: Annotated[
        Optional[str],
        Field(
            description=(
                "The existing reservation to use for instance provisioning."
                " Supports AWS Capacity Reservations and Capacity Blocks"
            )
        ),
    ] = None
    spot_policy: Annotated[
        Optional[SpotPolicy],
        Field(
            description="The policy for provisioning spot or on-demand instances: `spot`, `on-demand`, or `auto`. Defaults to `on-demand`"
        ),
    ] = None
    retry: Annotated[
        Optional[Union[ProfileRetry, bool]],
        Field(description="The policy for resubmitting the run. Defaults to `false`"),
    ] = None
    max_duration: Annotated[
        Optional[Union[Literal["off"], str, int, bool]],
        Field(
            description=(
                "The maximum duration of a run (e.g., `2h`, `1d`, etc)."
                " After it elapses, the run is automatically stopped."
                " Use `off` for unlimited duration. Defaults to `off`"
            )
        ),
    ] = None
    stop_duration: Annotated[
        Optional[Union[Literal["off"], str, int, bool]],
        Field(
            description=(
                "The maximum duration of a run graceful stopping."
                " After it elapses, the run is automatically forced stopped."
                " This includes force detaching volumes used by the run."
                " Use `off` for unlimited duration. Defaults to `5m`"
            )
        ),
    ] = None
    max_price: Annotated[
        Optional[float],
        Field(description="The maximum instance price per hour, in dollars", gt=0.0),
    ] = None
    creation_policy: Annotated[
        Optional[CreationPolicy],
        Field(
            description="The policy for using instances from fleets. Defaults to `reuse-or-create`"
        ),
    ] = None
    idle_duration: Annotated[
        Optional[Union[Literal["off"], str, int, bool]],
        Field(
            description=(
                "Time to wait before terminating idle instances."
                " Defaults to `5m` for runs and `3d` for fleets. Use `off` for unlimited duration"
            )
        ),
    ] = None
    utilization_policy: Annotated[
        Optional[UtilizationPolicy],
        Field(description="Run termination policy based on utilization"),
    ] = None
    fleets: Annotated[
        Optional[list[str]], Field(description="The fleets considered for reuse")
    ] = None
    tags: Annotated[
        Optional[Dict[str, str]],
        Field(
            description=(
                "The custom tags to associate with the resource."
                " The tags are also propagated to the underlying backend resources."
                " If there is a conflict with backend-level tags, does not override them"
            )
        ),
    ] = None

    # Deprecated and unused. Left for compatibility with 0.18 clients.
    pool_name: Annotated[Optional[str], Field(exclude=True)] = None
    instance_name: Annotated[Optional[str], Field(exclude=True)] = None
    retry_policy: Annotated[Optional[ProfileRetryPolicy], Field(exclude=True)] = None
    termination_policy: Annotated[Optional[TerminationPolicy], Field(exclude=True)] = None
    termination_idle_time: Annotated[Optional[Union[str, int]], Field(exclude=True)] = None

    class Config:
        @staticmethod
        def schema_extra(schema: Dict[str, Any]) -> None:
            del schema["properties"]["pool_name"]
            del schema["properties"]["instance_name"]
            del schema["properties"]["retry_policy"]
            del schema["properties"]["termination_policy"]
            del schema["properties"]["termination_idle_time"]

    _validate_max_duration = validator("max_duration", pre=True, allow_reuse=True)(
        parse_max_duration
    )
    _validate_stop_duration = validator("stop_duration", pre=True, allow_reuse=True)(
        parse_stop_duration
    )
    _validate_idle_duration = validator("idle_duration", pre=True, allow_reuse=True)(
        parse_idle_duration
    )
    _validate_tags = validator("tags", pre=True, allow_reuse=True)(tags_validator)


class ProfileProps(CoreModel):
    name: Annotated[
        str,
        Field(
            description="The name of the profile that can be passed as `--profile` to `dstack apply`"
        ),
    ]
    default: Annotated[
        bool, Field(description="If set to true, `dstack apply` will use this profile by default.")
    ] = False


class Profile(ProfileProps, ProfileParams):
    pass


class ProfilesConfig(CoreModel):
    profiles: List[Profile]

    class Config:
        schema_extra = {"$schema": "http://json-schema.org/draft-07/schema#"}

    def default(self) -> Optional[Profile]:
        for p in self.profiles:
            if p.default:
                return p
        return None

    def get(self, name: str) -> Profile:
        for p in self.profiles:
            if p.name == name:
                return p
        raise KeyError(name)
