import ipaddress
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import Field, root_validator, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import (
    ApplyAction,
    CoreConfig,
    CoreModel,
    generate_dual_core_model,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.instances import Instance, InstanceOfferWithAvailability, SSHKey
from dstack._internal.core.models.profiles import (
    Profile,
    ProfileParams,
    ProfileRetry,
    SpotPolicy,
    parse_idle_duration,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.utils.common import list_enum_values_for_annotation
from dstack._internal.utils.json_schema import add_extra_schema_types
from dstack._internal.utils.tags import tags_validator


class FleetStatus(str, Enum):
    # Currently all fleets are ACTIVE/TERMINATING/TERMINATED
    # SUBMITTED/FAILED may be used if fleets require async processing
    SUBMITTED = "submitted"
    ACTIVE = "active"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"


class InstanceGroupPlacement(str, Enum):
    ANY = "any"
    CLUSTER = "cluster"


class SSHProxyParams(CoreModel):
    hostname: Annotated[str, Field(description="The IP address or domain of proxy host")]
    port: Annotated[Optional[int], Field(description="The SSH port of proxy host")] = None
    user: Annotated[str, Field(description="The user to log in with for proxy host")]
    identity_file: Annotated[str, Field(description="The private key to use for proxy host")]
    ssh_key: Optional[SSHKey] = None


class SSHHostParams(CoreModel):
    hostname: Annotated[str, Field(description="The IP address or domain to connect to")]
    port: Annotated[
        Optional[int], Field(description="The SSH port to connect to for this host")
    ] = None
    user: Annotated[Optional[str], Field(description="The user to log in with for this host")] = (
        None
    )
    identity_file: Annotated[
        Optional[str], Field(description="The private key to use for this host")
    ] = None
    proxy_jump: Annotated[
        Optional[SSHProxyParams], Field(description="The SSH proxy configuration for this host")
    ] = None
    internal_ip: Annotated[
        Optional[str],
        Field(
            description=(
                "The internal IP of the host used for communication inside the cluster."
                " If not specified, `dstack` will use the IP address from `network` or from the first found internal network."
            )
        ),
    ] = None
    ssh_key: Optional[SSHKey] = None

    blocks: Annotated[
        Union[Literal["auto"], int],
        Field(
            description=(
                "The amount of blocks to split the instance into, a number or `auto`."
                " `auto` means as many as possible."
                " The number of GPUs and CPUs must be divisible by the number of blocks."
                " Defaults to `1`, i.e. do not split"
            ),
            ge=1,
        ),
    ] = 1

    @validator("internal_ip")
    def validate_internal_ip(cls, value):
        if value is None:
            return value
        try:
            internal_ip = ipaddress.ip_address(value)
        except ValueError as e:
            raise ValueError("Invalid IP address") from e
        if not internal_ip.is_private:
            raise ValueError("IP address is not private")
        return value


class SSHParams(CoreModel):
    user: Annotated[Optional[str], Field(description="The user to log in with on all hosts")] = (
        None
    )
    port: Annotated[Optional[int], Field(description="The SSH port to connect to")] = None
    identity_file: Annotated[
        Optional[str], Field(description="The private key to use for all hosts")
    ] = None
    ssh_key: Optional[SSHKey] = None
    proxy_jump: Annotated[
        Optional[SSHProxyParams], Field(description="The SSH proxy configuration for all hosts")
    ] = None
    hosts: Annotated[
        List[Union[SSHHostParams, str]],
        Field(
            description="The per host connection parameters: a hostname or an object that overrides default ssh parameters"
        ),
    ]
    network: Annotated[
        Optional[str],
        Field(
            description=(
                "The network address for cluster setup in the format `<ip>/<netmask>`."
                " `dstack` will use IP addresses from this network for communication between hosts."
                " If not specified, `dstack` will use IPs from the first found internal network."
            )
        ),
    ]

    @validator("network")
    def validate_network(cls, value):
        if value is None:
            return value
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as e:
            raise ValueError(f"Failed to parse network: {value}") from e
        if not network.is_private:
            raise ValueError("Public network is specified when private network is required")
        return value


class FleetNodesSpec(CoreModel):
    min: Annotated[
        int, Field(description=("The minimum number of instances to maintain in the fleet"))
    ]
    target: Annotated[
        int,
        Field(
            description=(
                "The number of instances to provision on fleet apply. `min` <= `target` <= `max`"
                " Defaults to `min`"
            )
        ),
    ]
    max: Annotated[
        Optional[int],
        Field(
            description=(
                "The maximum number of instances allowed in the fleet. Unlimited if not specified"
            )
        ),
    ] = None

    def dict(self, *args, **kwargs) -> Dict:
        # super() does not work with pydantic-duality
        res = CoreModel.dict(self, *args, **kwargs)
        # For backward compatibility with old clients
        # that do not ignore extra fields due to https://github.com/dstackai/dstack/issues/3066
        if "target" in res and res["target"] == res["min"]:
            del res["target"]
        return res

    @root_validator(pre=True)
    def set_min_and_target_defaults(cls, values):
        min_ = values.get("min")
        target = values.get("target")
        if min_ is None:
            values["min"] = 0
        if target is None:
            values["target"] = values["min"]
        return values

    @validator("min")
    def validate_min(cls, v: int) -> int:
        if v < 0:
            raise ValueError("min cannot be negative")
        return v

    @root_validator(skip_on_failure=True)
    def _post_validate_ranges(cls, values):
        min_ = values["min"]
        target = values["target"]
        max_ = values.get("max")
        if target < min_:
            raise ValueError("target must not be be less than min")
        if max_ is not None and max_ < min_:
            raise ValueError("max must not be less than min")
        if max_ is not None and max_ < target:
            raise ValueError("max must not be less than target")
        return values


class InstanceGroupParamsConfig(CoreConfig):
    @staticmethod
    def schema_extra(schema: Dict[str, Any]):
        add_extra_schema_types(
            schema["properties"]["nodes"],
            extra_types=[{"type": "integer"}, {"type": "string"}],
        )
        add_extra_schema_types(
            schema["properties"]["idle_duration"],
            extra_types=[{"type": "string"}],
        )


class InstanceGroupParams(CoreModel):
    env: Annotated[
        Env,
        Field(description="The mapping or the list of environment variables"),
    ] = Env()
    ssh_config: Annotated[
        Optional[SSHParams],
        Field(description="The parameters for adding instances via SSH"),
    ] = None

    nodes: Annotated[
        Optional[FleetNodesSpec], Field(description="The number of instances in cloud fleet")
    ] = None
    placement: Annotated[
        Optional[InstanceGroupPlacement],
        Field(description="The placement of instances: `any` or `cluster`"),
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
    resources: Annotated[
        Optional[ResourcesSpec],
        Field(description="The resources requirements"),
    ] = ResourcesSpec()

    blocks: Annotated[
        Union[Literal["auto"], int],
        Field(
            description=(
                "The amount of blocks to split the instance into, a number or `auto`."
                " `auto` means as many as possible."
                " The number of GPUs and CPUs must be divisible by the number of blocks."
                " Defaults to `1`, i.e. do not split"
            ),
            ge=1,
        ),
    ] = 1

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
        Field(description="The policy for provisioning retry. Defaults to `false`"),
    ] = None
    max_price: Annotated[
        Optional[float],
        Field(description="The maximum instance price per hour, in dollars", gt=0.0),
    ] = None
    idle_duration: Annotated[
        Optional[int],
        Field(
            description=(
                "Time to wait before terminating idle instances."
                " Instances are not terminated if the fleet is already at `nodes.min`."
                " Defaults to `5m` for runs and `3d` for fleets."
                " Use `off` for unlimited duration"
            )
        ),
    ] = None

    @validator("nodes", pre=True)
    def parse_nodes(cls, v: Optional[Union[dict, str]]) -> Optional[dict]:
        if isinstance(v, str) and ".." in v:
            v = v.replace(" ", "")
            min, max = v.split("..")
            return dict(min=min or None, max=max or None)
        elif isinstance(v, str) or isinstance(v, int):
            return dict(min=v, max=v)
        return v

    _validate_idle_duration = validator("idle_duration", pre=True, allow_reuse=True)(
        parse_idle_duration
    )


class FleetProps(CoreModel):
    type: Literal["fleet"] = "fleet"
    name: Annotated[Optional[str], Field(description="The fleet name")] = None


class FleetConfigurationConfig(InstanceGroupParamsConfig):
    @staticmethod
    def schema_extra(schema: Dict[str, Any]):
        InstanceGroupParamsConfig.schema_extra(schema)


class FleetConfiguration(
    InstanceGroupParams,
    FleetProps,
    generate_dual_core_model(FleetConfigurationConfig),
):
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

    _validate_tags = validator("tags", pre=True, allow_reuse=True)(tags_validator)


class FleetSpecConfig(CoreConfig):
    @staticmethod
    def schema_extra(schema: Dict[str, Any]):
        prop = schema.get("properties", {})
        prop.pop("merged_profile", None)


class FleetSpec(generate_dual_core_model(FleetSpecConfig)):
    configuration: FleetConfiguration
    configuration_path: Optional[str] = None
    profile: Profile
    autocreated: bool = False
    # merged_profile stores profile parameters merged from profile and configuration.
    # Read profile parameters from merged_profile instead of profile directly.
    # TODO: make merged_profile a computed field after migrating to pydanticV2
    merged_profile: Annotated[Profile, Field(exclude=True)] = None

    @root_validator
    def _merged_profile(cls, values) -> Dict:
        try:
            merged_profile = Profile.parse_obj(values["profile"])
            conf = FleetConfiguration.parse_obj(values["configuration"])
        except KeyError:
            raise ValueError("Missing profile or configuration")
        for key in ProfileParams.__fields__:
            conf_val = getattr(conf, key, None)
            if conf_val is not None:
                setattr(merged_profile, key, conf_val)
        if merged_profile.spot_policy is None:
            merged_profile.spot_policy = SpotPolicy.ONDEMAND
        if merged_profile.retry is None:
            merged_profile.retry = False
        values["merged_profile"] = merged_profile
        return values


class Fleet(CoreModel):
    id: uuid.UUID
    name: str
    project_name: str
    spec: FleetSpec
    created_at: datetime
    status: FleetStatus
    status_message: Optional[str] = None
    instances: List[Instance]


class FleetPlan(CoreModel):
    project_name: str
    user: str
    spec: FleetSpec
    effective_spec: Optional[FleetSpec] = None
    current_resource: Optional[Fleet] = None
    offers: List[InstanceOfferWithAvailability]
    total_offers: int
    max_offer_price: Optional[float] = None
    action: Optional[ApplyAction] = None  # default value for backward compatibility

    def get_effective_spec(self) -> FleetSpec:
        if self.effective_spec is not None:
            return self.effective_spec
        return self.spec


class ApplyFleetPlanInput(CoreModel):
    spec: FleetSpec
    current_resource: Annotated[
        Optional[Fleet],
        Field(
            description=(
                "The expected current resource."
                " If the resource has changed, the apply fails unless `force: true`."
            )
        ),
    ] = None
