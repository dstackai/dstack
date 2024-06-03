from enum import Enum
from typing import List, Optional, Union

from pydantic import Field, root_validator, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel, Duration

DEFAULT_RETRY_DURATION = 3600
DEFAULT_POOL_NAME = "default-pool"

DEFAULT_RUN_TERMINATION_IDLE_TIME = 5 * 60  # 5 minutes
DEFAULT_POOL_TERMINATION_IDLE_TIME = 72 * 60 * 60  # 3 days

DEFAULT_INSTANCE_RETRY_DURATION = 60 * 60 * 24  # 24h


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


def parse_duration(v: Optional[Union[int, str]]) -> Optional[int]:
    if v is None:
        return None
    return Duration.parse(v)


def parse_max_duration(v: Optional[Union[int, str]]) -> Optional[Union[str, int]]:
    if v == "off":
        return v
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
    instance_types: Annotated[
        Optional[List[str]],
        Field(
            description="The cloud-specific instance types to consider for provisioning (e.g., `[p3.8xlarge, n1-standard-4]`)"
        ),
    ]
    spot_policy: Annotated[
        Optional[SpotPolicy],
        Field(
            description="The policy for provisioning spot or on-demand instances: `spot`, `on-demand`, or `auto`"
        ),
    ]
    retry: Annotated[
        Optional[Union[ProfileRetry, bool]],
        Field(description="The policy for resubmitting the run. Defaults to `false`"),
    ]
    retry_policy: Annotated[
        Optional[ProfileRetryPolicy],
        Field(description="The policy for resubmitting the run. Deprecated in favor of `retry`"),
    ]
    max_duration: Annotated[
        Optional[Union[Literal["off"], str, int]],
        Field(
            description="The maximum duration of a run (e.g., `2h`, `1d`, etc). After it elapses, the run is forced to stop. Defaults to `off`"
        ),
    ]
    max_price: Annotated[
        Optional[float], Field(description="The maximum price per hour, in dollars", gt=0.0)
    ]
    pool_name: Annotated[
        Optional[str],
        Field(description="The name of the pool. If not set, dstack will use the default name"),
    ]
    instance_name: Annotated[Optional[str], Field(description="The name of the instance")]
    creation_policy: Annotated[
        Optional[CreationPolicy],
        Field(
            description="The policy for using instances from the pool. Defaults to `reuse-or-create`"
        ),
    ]
    termination_policy: Annotated[
        Optional[TerminationPolicy],
        Field(
            description="The policy for termination instances. Defaults to `destroy-after-idle`"
        ),
    ]
    termination_idle_time: Annotated[
        Optional[Union[str, int]],
        Field(
            description="Time to wait before destroying the idle instance. Defaults to `5m` for `dstack run` and to `3d` for `dstack pool add`"
        ),
    ]

    _validate_max_duration = validator("max_duration", pre=True, allow_reuse=True)(
        parse_max_duration
    )
    _validate_termination_idle_time = validator(
        "termination_idle_time", pre=True, allow_reuse=True
    )(parse_duration)


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
