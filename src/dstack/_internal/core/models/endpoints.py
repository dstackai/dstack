import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import Field, validator

from dstack._internal.core.models.common import (
    ApplyAction,
    CoreModel,
    generate_dual_core_model,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.profiles import ProfileParams, ProfileParamsConfig
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.utils.json_schema import add_extra_schema_types


class EndpointStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    PROTOTYPING = "prototyping"
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
        add_extra_schema_types(
            schema["properties"]["model"],
            extra_types=[{"type": "string"}],
        )


class EndpointModelRepo(CoreModel):
    repo: str
    """Exact repo/path to deploy."""
    name: Optional[str] = None
    """API-facing model name. Defaults to `repo`."""

    @property
    def api_model_name(self) -> str:
        return self.name or self.repo

    @property
    def exact_repo(self) -> str:
        return self.repo

    @property
    def allows_variant_selection(self) -> bool:
        return False

    @validator("repo")
    def validate_repo(cls, v: str) -> str:
        return _validate_endpoint_model_string(v, field_name="repo")

    @validator("name")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_endpoint_model_string(v, field_name="name")


class EndpointModelBase(CoreModel):
    base: str
    """Base model name. The agent may choose a compatible repo/path to deploy."""

    @property
    def api_model_name(self) -> str:
        return self.base

    @property
    def exact_repo(self) -> None:
        return None

    @property
    def allows_variant_selection(self) -> bool:
        return True

    @validator("base")
    def validate_base(cls, v: str) -> str:
        return _validate_endpoint_model_string(v, field_name="base")


EndpointModelSpec = Union[EndpointModelRepo, EndpointModelBase]


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
        EndpointModelSpec,
        Field(
            description=(
                "The model to serve. Use a string or `repo` for an exact repo/path, "
                "or `base` to let the endpoint agent choose a compatible variant."
            )
        ),
    ]
    env: Annotated[
        Env,
        Field(description="The mapping or the list of environment variables"),
    ] = Env()
    # TODO: Add endpoint-level resources only with hard scheduling semantics for both
    # single-service and replica-group presets. V1 intentionally relies on preset/service
    # resources plus ProfileParams constraints.
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

    @validator("model", pre=True)
    def parse_model(cls, v) -> dict | EndpointModelSpec:
        if isinstance(v, str):
            return {"repo": _validate_endpoint_model_string(v, field_name="model")}
        return v


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
    model_base: Optional[str] = None
    """Base model repo for the endpoint's current deployed model."""
    model_repo: Optional[str] = None
    """Exact repo/path deployed by the endpoint's current service."""
    error: Optional[str] = None


class EndpointProvisioningPlanNone(CoreModel):
    type: Literal["none"] = "none"
    reason: str


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
    preset_base: str
    recipe_id: str
    service_name: str
    job_offers: list[EndpointPlanJobOffers]


class EndpointProvisioningPlanAgent(CoreModel):
    type: Literal["agent"] = "agent"
    agent_model: str
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


def _validate_endpoint_model_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Endpoint model {field_name} must be a non-empty string")
    return value
