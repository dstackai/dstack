import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import (
    ApplyAction,
    CoreModel,
    generate_dual_core_model,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.profiles import ProfileParams, ProfileParamsConfig
from dstack._internal.core.models.resources import ResourcesSpec


class EndpointStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    CLAUDING = "clauding"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"

    @classmethod
    def finished_statuses(cls) -> list["EndpointStatus"]:
        return [cls.STOPPED, cls.FAILED]

    def is_finished(self) -> bool:
        return self in self.finished_statuses()


class EndpointPresetPolicy(str, Enum):
    REUSE = "reuse"
    CREATE = "create"
    REUSE_OR_CREATE = "reuse-or-create"


class EndpointConfigurationConfig(ProfileParamsConfig):
    @staticmethod
    def schema_extra(schema: dict):
        ProfileParamsConfig.schema_extra(schema)


class EndpointConfiguration(
    ProfileParams,
    generate_dual_core_model(EndpointConfigurationConfig),
):
    type: Literal["endpoint"] = "endpoint"
    name: Annotated[
        Optional[str],
        Field(description="The endpoint name. If not specified, a random name is generated"),
    ] = None
    model: Annotated[
        str,
        Field(description="The model to serve, typically a Hugging Face model ID"),
    ]
    env: Annotated[
        Env,
        Field(description="The mapping or the list of environment variables"),
    ] = Env()
    preset_policy: Annotated[
        EndpointPresetPolicy,
        Field(
            description=(
                "The policy for endpoint presets. `reuse` uses an existing preset only, "
                "`create` asks the server agent to create and save a new preset, and "
                "`reuse-or-create` first tries an existing preset and falls back to `create`."
            )
        ),
    ] = EndpointPresetPolicy.REUSE_OR_CREATE
    max_agent_budget: Annotated[
        Optional[float],
        Field(
            description=(
                "The maximum agent spend for provisioning this endpoint, in dollars. "
                "If not specified, the server default is used."
            ),
            gt=0.0,
        ),
    ] = None


class Endpoint(CoreModel):
    id: uuid.UUID
    name: str
    project_name: str
    user: str
    configuration: EndpointConfiguration
    created_at: datetime
    last_processed_at: datetime
    status: EndpointStatus
    status_message: Optional[str] = None
    run_name: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class EndpointProvisioningPlanNone(CoreModel):
    type: Literal["none"] = "none"
    reason: str


class EndpointPlanReplicaSpecGroup(CoreModel):
    """Ordered to match service replica groups; "0" is the implicit group."""

    name: str
    resources: ResourcesSpec
    """Per-replica scheduling requirements used for offer matching."""
    tested_resources: list[ResourcesSpec]
    """Exact resources of the replicas that were running when the preset was verified."""


class EndpointPlanJobOffers(CoreModel):
    replica_group: str
    resources: ResourcesSpec
    spot: Optional[bool]
    max_price: Optional[float]
    offers: list[InstanceOfferWithAvailability]
    total_offers: int
    max_offer_price: Optional[float]


class EndpointProvisioningPlanPreset(CoreModel):
    type: Literal["preset"] = "preset"
    preset_name: str
    service_name: str
    replica_spec_groups: list[EndpointPlanReplicaSpecGroup]
    job_offers: list[EndpointPlanJobOffers]


class EndpointProvisioningPlanAgent(CoreModel):
    type: Literal["agent"] = "agent"
    agent_model: str
    max_budget: Optional[float] = None
    reason: Optional[str] = None


AnyEndpointProvisioningPlan = Union[
    EndpointProvisioningPlanNone,
    EndpointProvisioningPlanPreset,
    EndpointProvisioningPlanAgent,
]


class EndpointPlan(CoreModel):
    project_name: str
    user: str
    configuration: EndpointConfiguration
    configuration_path: Optional[str] = None
    current_resource: Optional[Endpoint] = None
    action: ApplyAction
    preset_policy: EndpointPresetPolicy
    provisioning_plan: Annotated[AnyEndpointProvisioningPlan, Field(discriminator="type")]
