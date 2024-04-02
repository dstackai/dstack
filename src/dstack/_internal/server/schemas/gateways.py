from typing import List, Optional

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel


class CreateGatewayRequest(CoreModel):
    name: Optional[str]
    backend_type: BackendType
    region: str


class GetGatewayRequest(CoreModel):
    name: str


class DeleteGatewaysRequest(CoreModel):
    names: List[str]


class SetDefaultGatewayRequest(CoreModel):
    name: str


class SetWildcardDomainRequest(CoreModel):
    name: str
    wildcard_domain: str
