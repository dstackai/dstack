from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from typing_extensions import Annotated, Self

from dstack._internal.core.backends.profile_options import AnyBackendProfileOptions
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import (
    JSON_SCHEMA_DIALECT,
    CoreModel,
    EntityReference,
)
from dstack._internal.core.models.duration import (
    Duration,
    OptionalIdleDuration,
    OptionalOffableDuration,
)
from dstack._internal.utils.common import list_enum_values_for_annotation
from dstack._internal.utils.cron import validate_cron
from dstack._internal.utils.tags import tags_validator

DEFAULT_RETRY_DURATION = Duration(3600)

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


class StartupOrder(str, Enum):
    ANY = "any"
    MASTER_FIRST = "master-first"
    WORKERS_FIRST = "workers-first"


class StopCriteria(str, Enum):
    ALL_DONE = "all-done"
    MASTER_DONE = "master-done"


def validate_backend_options(
    v: Optional[List["AnyBackendProfileOptions"]],
) -> Optional[List["AnyBackendProfileOptions"]]:
    if v is None:
        return v
    seen = set()
    for opt in v:
        if opt.type in seen:
            raise ValueError(f"backend_options contains duplicate entry for backend '{opt.type}'")
        seen.add(opt.type)
    return v


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
                f" Supported events are {list_enum_values_for_annotation(RetryEvent)}."
                " Omit to retry on all events"
            )
        ),
    ] = None
    duration: Annotated[
        Optional[Duration],
        Field(
            description=(
                "The maximum period of retrying the run, e.g., `4h` or `1d`."
                " The period is calculated as a run age for `no-capacity` event"
                " and as a time passed since the last `interruption` and `error` for `interruption` and `error` events."
            )
        ),
    ] = None

    @model_validator(mode="after")
    def _validate_fields(self) -> Self:
        on_events = self.on_events
        if on_events is not None and len(self.on_events) == 0:
            raise ValueError("`on_events` cannot be empty")
        return self


MIN_UTILIZATION_TIME_WINDOW = "5m"


class UtilizationPolicy(CoreModel):
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
        Duration,
        Field(
            description=(
                "The time window of metric samples taking into account to measure utilization"
                f" (e.g., `30m`, `1h`). Minimum is `{MIN_UTILIZATION_TIME_WINDOW}`"
            )
        ),
    ]

    @field_validator("time_window")
    @classmethod
    def validate_time_window(cls, v: Duration) -> Duration:
        if v < Duration.parse(MIN_UTILIZATION_TIME_WINDOW):
            raise ValueError(f"Minimum time_window is {MIN_UTILIZATION_TIME_WINDOW}")
        return v


class Schedule(CoreModel):
    cron: Annotated[
        Union[List[str], str],
        Field(
            description=(
                "A cron expression or a list of cron expressions specifying the UTC time when the run needs to be started"
            )
        ),
    ]

    @field_validator("cron")
    @classmethod
    def _validate_cron(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            values = [v]
        else:
            values = v
        if len(values) == 0:
            raise ValueError("At least one cron expression must be specified")
        for value in values:
            validate_cron(value)
        return values

    @property
    def crons(self) -> List[str]:
        """
        Access `cron` attribute as a list.
        """
        if isinstance(self.cron, str):
            return [self.cron]
        return self.cron


class InstanceNameSelector(CoreModel):
    name: Annotated[str, Field(description="The fleet instance name", min_length=1)]


class InstanceHostnameSelector(CoreModel):
    hostname: Annotated[
        str, Field(description="The fleet instance hostname or IP address", min_length=1)
    ]


def _parse_fleet_instance_selector_fleet(v: Any) -> Any:
    if isinstance(v, str):
        return EntityReference.parse(v)
    return v


class FleetInstanceSelector(CoreModel):
    fleet: Annotated[
        EntityReference,
        Field(
            description=(
                "The fleet reference. For fleets owned by the current project, specify"
                " the fleet name. For a fleet from another project, specify"
                " `<project name>/<fleet name>` or an object with `project` and `name`."
            ),
        ),
    ]
    instance: Annotated[int, Field(description="The fleet instance number", ge=0)]

    _validate_fleet = field_validator(
        "fleet", mode="before", json_schema_input_type=Union[EntityReference, str]
    )(_parse_fleet_instance_selector_fleet)


InstanceSelector = Union[InstanceNameSelector, InstanceHostnameSelector, FleetInstanceSelector]


def parse_instance_selector(v: Union[InstanceSelector, str]) -> InstanceSelector:
    if isinstance(v, str):
        return InstanceNameSelector(name=v)
    return v


FleetReferenceOrShorthand = Annotated[
    Union[
        EntityReference,
        str,  # For server response compatibility with pre-0.20.14 clients
    ],
    AfterValidator(EntityReference.parse),
]
InstanceSelectorOrShorthand = Annotated[
    InstanceSelector,
    BeforeValidator(parse_instance_selector, json_schema_input_type=Union[InstanceSelector, str]),
]


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
            description="The cloud-specific instance types to consider for provisioning (e.g., `[g6e.24xlarge, n1-standard-4]`)"
        ),
    ] = None
    reservation: Annotated[
        Optional[str],
        Field(
            description=(
                "The existing reservation to use for instance provisioning."
                " Supports AWS Capacity Reservations, AWS Capacity Blocks, and GCP reservations"
            )
        ),
    ] = None
    spot_policy: Annotated[
        Optional[SpotPolicy],
        Field(
            description=(
                "The policy for provisioning spot or on-demand instances:"
                f" {list_enum_values_for_annotation(SpotPolicy)}."
                f" Defaults to `{SpotPolicy.ONDEMAND.value}`"
            )
        ),
    ] = None
    retry: Annotated[
        Optional[Union[ProfileRetry, bool]],
        Field(description="The policy for resubmitting the run. Defaults to `false`"),
    ] = None
    max_duration: Annotated[
        OptionalOffableDuration,
        Field(
            description=(
                "The maximum duration of a run (e.g., `2h`, `1d`, etc)"
                " in a running state, excluding provisioning and pulling."
                " After it elapses, the run is automatically stopped."
                " Use `off` for unlimited duration. Defaults to `off`"
            )
        ),
    ] = None
    stop_duration: Annotated[
        OptionalOffableDuration,
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
            description=(
                "The policy for using instances from fleets:"
                f" {list_enum_values_for_annotation(CreationPolicy)}."
                f" Defaults to `{CreationPolicy.REUSE_OR_CREATE.value}`"
            )
        ),
    ] = None
    idle_duration: Annotated[
        OptionalIdleDuration,
        Field(
            description=(
                "Time to wait before terminating idle instances."
                " When the run reuses an existing fleet instance, the fleet's `idle_duration` applies."
                " When the run provisions a new instance, the shorter of the fleet's and run's values is used."
                " Defaults to `5m` for runs and `3d` for fleets."
                " Use `off` for unlimited duration."
                " Only applied for VM-based backends"
            )
        ),
    ] = None
    utilization_policy: Annotated[
        Optional[UtilizationPolicy],
        Field(description="Run termination policy based on utilization"),
    ] = None
    startup_order: Annotated[
        Optional[StartupOrder],
        Field(
            description=(
                f"The order in which master and workers jobs are started:"
                f" {list_enum_values_for_annotation(StartupOrder)}."
                f" Defaults to `{StartupOrder.ANY.value}`"
            )
        ),
    ] = None
    stop_criteria: Annotated[
        Optional[StopCriteria],
        Field(
            description=(
                "The criteria determining when a multi-node run should be considered finished:"
                f" {list_enum_values_for_annotation(StopCriteria)}."
                f" Defaults to `{StopCriteria.ALL_DONE.value}`"
            )
        ),
    ] = None
    schedule: Annotated[
        Optional[Schedule],
        Field(description=("The schedule for starting the run at specified time")),
    ] = None
    fleets: Annotated[
        Optional[list[FleetReferenceOrShorthand]],
        Field(
            description=(
                "The fleets considered for reuse."
                " For fleets owned by the current project, specify fleet names."
                " For imported fleets, specify `<project name>/<fleet name>`"
            ),
        ),
    ] = None
    instances: Annotated[
        Optional[List[InstanceSelectorOrShorthand]],
        Field(
            description=(
                "The specific fleet instances to consider for reuse."
                " Each value can be an instance name string, or an object with"
                " `name`, `hostname`, or `fleet` and `instance`."
                " When set, the run is only placed on matching existing instances."
            ),
            min_length=1,
        ),
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
    backend_options: Annotated[
        Optional[List[AnyBackendProfileOptions]],
        Field(description="Backend-specific options, applied only to offers from that backend"),
    ] = None

    _validate_tags = field_validator("tags", mode="before")(tags_validator)
    _validate_backend_options = field_validator("backend_options")(validate_backend_options)


class ProfileProps(CoreModel):
    name: Annotated[
        str,
        Field(
            description="The name of the profile that can be passed as `--profile` to `dstack apply`"
        ),
    ] = ""
    default: Annotated[
        bool, Field(description="If set to true, `dstack apply` will use this profile by default.")
    ] = False


class Profile(
    ProfileProps,
    ProfileParams,
):
    pass


class ProfilesConfig(CoreModel):
    model_config = ConfigDict(json_schema_extra={"$schema": JSON_SCHEMA_DIALECT})

    profiles: List[Profile]

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
