from typing import Annotated, Any, Dict, List, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreConfig, CoreModel, generate_dual_core_model
from dstack._internal.core.models.gateways import (
    ApplyGatewayPlanInput,
    GatewayConfiguration,
    GatewaySpec,
)


class CreateGatewayRequestConfig(CoreConfig):
    @staticmethod
    def schema_extra(schema: Dict[str, Any]):
        pass


class CreateGatewayRequest(generate_dual_core_model(CreateGatewayRequestConfig)):
    configuration: GatewayConfiguration


class ListGatewaysRequest(CoreModel):
    include_imported: bool = False


class GetGatewayRequest(CoreModel):
    name: str


class GetGatewayPlanRequest(CoreModel):
    spec: GatewaySpec


class ApplyGatewayPlanRequest(CoreModel):
    plan: ApplyGatewayPlanInput
    force: Annotated[
        bool,
        Field(
            description="Use `force: true` to apply even if the expected resource does not match."
        ),
    ]


class DeleteGatewaysRequest(CoreModel):
    names: List[str]


class SetDefaultGatewayRequest(CoreModel):
    name: str
    gateway_project: Optional[str] = None


class SetWildcardDomainRequest(CoreModel):
    name: str
    wildcard_domain: str
