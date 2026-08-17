from typing import Annotated, Any, List, Optional

from pydantic import Field, model_validator

from dstack._internal.core.models.common import CoreModel, pop_null_field
from dstack._internal.core.models.gateways import (
    ApplyGatewayPlanInput,
    GatewayConfiguration,
    GatewaySpec,
)


class CreateGatewayRequest(CoreModel):
    configuration: GatewayConfiguration


class ListGatewaysRequest(CoreModel):
    include_imported: bool = False


class GetGatewayRequest(CoreModel):
    name: str


class GetGatewayPlanRequest(CoreModel):
    spec: GatewaySpec

    @model_validator(mode="before")
    @classmethod
    def _drop_null_router(cls, values: Any) -> Any:
        # Compatibility with 0.20.27, 0.20.28, 0.20.29 clients
        return pop_null_field(values, "spec", "configuration", "router")


class ApplyGatewayPlanRequest(CoreModel):
    plan: ApplyGatewayPlanInput
    force: Annotated[
        bool,
        Field(
            description="Use `force: true` to apply even if the expected resource does not match."
        ),
    ]

    @model_validator(mode="before")
    @classmethod
    def _drop_null_router(cls, values: Any) -> Any:
        # Compatibility with 0.20.27, 0.20.28, 0.20.29 clients
        values = pop_null_field(values, "plan", "spec", "configuration", "router")
        values = pop_null_field(values, "plan", "current_resource", "configuration", "router")
        return values


class DeleteGatewaysRequest(CoreModel):
    names: List[str]


class SetDefaultGatewayRequest(CoreModel):
    name: str
    gateway_project: Optional[str] = None


class SetWildcardDomainRequest(CoreModel):
    name: str
    wildcard_domain: str
