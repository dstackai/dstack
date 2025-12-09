from typing import Any, Dict, List

from dstack._internal.core.models.common import CoreConfig, CoreModel, generate_dual_core_model
from dstack._internal.core.models.gateways import GatewayConfiguration


class CreateGatewayRequestConfig(CoreConfig):
    @staticmethod
    def schema_extra(schema: Dict[str, Any]):
        pass


class CreateGatewayRequest(generate_dual_core_model(CreateGatewayRequestConfig)):
    configuration: GatewayConfiguration


class GetGatewayRequest(CoreModel):
    name: str


class DeleteGatewaysRequest(CoreModel):
    names: List[str]


class SetDefaultGatewayRequest(CoreModel):
    name: str


class SetWildcardDomainRequest(CoreModel):
    name: str
    wildcard_domain: str
