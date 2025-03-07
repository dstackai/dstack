from enum import Enum
from typing import List, Optional, Union, overload

from pydantic import Field, root_validator, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel, Duration

DEFAULT_RETRY_DURATION = 3600
DEFAULT_POOL_NAME = "default-pool"

DEFAULT_RUN_TERMINATION_IDLE_TIME = 5 * 60  # 5 minutes
DEFAULT_POOL_TERMINATION_IDLE_TIME = 72 * 60 * 60  # 3 days

DEFAULT_INSTANCE_RETRY_DURATION = 60 * 60 * 24  # 24h

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
        List[RetryEvent],
        Field(
            description=(
                "The list of events that should be handled with retry."
                " Supported events are `no-capacity`, `interruption`, and `error`"
            )
        ),
    ]
    duration: Annotated[
        Optional[Union[int, str]],
        Field(description="The maximum period of retrying the run, e.g., `4h` or `1d`"),
    ] = None

    _validate_duration = validator("duration", pre=True, allow_reuse=True)(parse_duration)

    @root_validator
    def _validate_fields(cls, values):
        if "on_events" in values and len(values["on_events"]) == 0:
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
    ]
    regions: Annotated[
        Optional[List[str]],
        Field(
            description="The regions to consider for provisioning (e.g., `[eu-west-1, us-west4, westeurope]`)"
        ),
    ]
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
    ]
    reservation: Annotated[
        Optional[str],
        Field(
            description=(
                "The existing reservation to use for instance provisioning."
                " Supports AWS Capacity Reservations and Capacity Blocks"
            )
        ),
    ]
    spot_policy: Annotated[
        Optional[SpotPolicy],
        Field(
            description="The policy for provisioning spot or on-demand instances: `spot`, `on-demand`, or `auto`. Defaults to `on-demand`"
        ),
    ]
    retry: Annotated[
        Optional[Union[ProfileRetry, bool]],
        Field(description="The policy for resubmitting the run. Defaults to `false`"),
    ]
    max_duration: Annotated[
        Optional[Union[Literal["off"], str, int, bool]],
        Field(
            description=(
                "The maximum duration of a run (e.g., `2h`, `1d`, etc)."
                " After it elapses, the run is automatically stopped."
                " Use `off` for unlimited duration. Defaults to `off`"
            )
        ),
    ]
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
    ]
    max_price: Annotated[
        Optional[float],
        Field(description="The maximum instance price per hour, in dollars", gt=0.0),
    ]
    creation_policy: Annotated[
        Optional[CreationPolicy],
        Field(
            description="The policy for using instances from the pool. Defaults to `reuse-or-create`"
        ),
    ]
    idle_duration: Annotated[
        Optional[Union[Literal["off"], str, int, bool]],
        Field(
            description=(
                "Time to wait before terminating idle instances."
                " Defaults to `5m` for runs and `3d` for fleets. Use `off` for unlimited duration"
            )
        ),
    ]
    utilization_policy: Annotated[
        Optional[UtilizationPolicy],
        Field(description="Run termination policy based on utilization"),
    ]
    # Deprecated:
    termination_policy: Annotated[
        Optional[TerminationPolicy],
        Field(
            description="Deprecated in favor of `idle_duration`",
        ),
    ]
    termination_idle_time: Annotated[
        Optional[Union[str, int]],
        Field(
            description="Deprecated in favor of `idle_duration`",
        ),
    ]
    # The name of the pool. If not set, dstack will use the default name
    pool_name: Optional[str]
    # The name of the instance
    instance_name: Optional[str]
    # The policy for resubmitting the run. Deprecated in favor of `retry`
    retry_policy: Optional[ProfileRetryPolicy]

    _validate_max_duration = validator("max_duration", pre=True, allow_reuse=True)(
        parse_max_duration
    )
    _validate_stop_duration = validator("stop_duration", pre=True, allow_reuse=True)(
        parse_stop_duration
    )
    _validate_termination_idle_time = validator(
        "termination_idle_time", pre=True, allow_reuse=True
    )(parse_duration)
    _validate_idle_duration = validator("idle_duration", pre=True, allow_reuse=True)(
        parse_idle_duration
    )


class ProfileProps(CoreModel):
    name: Annotated[
        str,
        Field(
            description="The name of the profile that can be passed as `--profile` to `dstack run`"
        ),
    ]
    default: Annotated[
        bool, Field(description="If set to true, `dstack run` will use this profile by default.")
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
