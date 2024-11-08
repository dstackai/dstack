import ipaddress
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import Field, root_validator, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.instances import InstanceOfferWithAvailability, SSHKey
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_TERMINATION_IDLE_TIME,
    Profile,
    ProfileParams,
    ProfileRetry,
    SpotPolicy,
    TerminationPolicy,
    parse_duration,
)
from dstack._internal.core.models.resources import Range, ResourcesSpec


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
    ssh_key: Optional[SSHKey] = None


class SSHParams(CoreModel):
    user: Annotated[Optional[str], Field(description="The user to log in with on all hosts")] = (
        None
    )
    port: Annotated[Optional[int], Field(description="The SSH port to connect to")] = None
    identity_file: Annotated[
        Optional[str], Field(description="The private key to use for all hosts")
    ] = None
    ssh_key: Optional[SSHKey] = None
    hosts: Annotated[
        List[Union[SSHHostParams, str]],
        Field(
            description="The per host connection parameters: a hostname or an object that overrides default ssh parameters"
        ),
    ]
    network: Annotated[
        Optional[str],
        Field(description="The network address for cluster setup in the format `<ip>/<netmask>`"),
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


class InstanceGroupParams(CoreModel):
    env: Annotated[
        Env,
        Field(description="The mapping or the list of environment variables"),
    ] = Env()
    ssh_config: Annotated[
        Optional[SSHParams],
        Field(description="The parameters for adding instances via SSH"),
    ] = None

    nodes: Annotated[Optional[Range[int]], Field(description="The number of instances")] = None
    placement: Annotated[
        Optional[InstanceGroupPlacement],
        Field(description="The placement of instances: `any` or `cluster`"),
    ] = None
    reservation: Annotated[
        Optional[str],
        Field(description="The existing reservation for the instances"),
    ] = None
    resources: Annotated[
        Optional[ResourcesSpec],
        Field(description="The resources requirements"),
    ] = ResourcesSpec()

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
    instance_types: Annotated[
        Optional[List[str]],
        Field(
            description="The cloud-specific instance types to consider for provisioning (e.g., `[p3.8xlarge, n1-standard-4]`)"
        ),
    ] = None
    spot_policy: Annotated[
        Optional[SpotPolicy],
        Field(
            description="The policy for provisioning spot or on-demand instances: `spot`, `on-demand`, or `auto`"
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
    termination_policy: Annotated[
        Optional[TerminationPolicy],
        Field(description="The policy for instance termination. Defaults to `destroy-after-idle`"),
    ] = None
    termination_idle_time: Annotated[
        Optional[Union[str, int]],
        Field(description="Time to wait before destroying idle instances. Defaults to `3d`"),
    ] = None

    _validate_termination_idle_time = validator(
        "termination_idle_time", pre=True, allow_reuse=True
    )(parse_duration)


class FleetProps(CoreModel):
    type: Literal["fleet"] = "fleet"
    name: Annotated[Optional[str], Field(description="The fleet name")] = None


class FleetConfiguration(InstanceGroupParams, FleetProps):
    pass


class FleetSpec(CoreModel):
    configuration: FleetConfiguration
    configuration_path: Optional[str] = None
    profile: Profile
    autocreated: bool = False
    # TODO: make merged_profile a computed field after migrating to pydanticV2
    merged_profile: Annotated[Profile, Field(exclude=True)] = None

    class Config:
        @staticmethod
        def schema_extra(schema: Dict[str, Any], model: Type) -> None:
            prop = schema.get("properties", {})
            prop.pop("merged_profile", None)

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
        if merged_profile.termination_policy is None:
            merged_profile.termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        if merged_profile.termination_idle_time is None:
            merged_profile.termination_idle_time = DEFAULT_POOL_TERMINATION_IDLE_TIME
        values["merged_profile"] = merged_profile
        return values


class Fleet(CoreModel):
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
    current_resource: Optional[Fleet]
    offers: List[InstanceOfferWithAvailability]
    total_offers: int
    max_offer_price: Optional[float]
