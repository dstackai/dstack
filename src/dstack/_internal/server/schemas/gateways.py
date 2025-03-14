from typing import List

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gateways import GatewayConfiguration


class CreateGatewayRequest(CoreModel):
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
