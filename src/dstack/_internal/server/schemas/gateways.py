from typing import Dict, List, Optional

from pydantic import root_validator

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gateways import GatewayConfiguration


class CreateGatewayRequest(CoreModel):
    name: Optional[str]
    backend_type: Optional[BackendType]
    region: Optional[str]
    configuration: Optional[GatewayConfiguration]

    @root_validator
    def fill_configuration(cls, values: Dict) -> Dict:
        if values.get("configuration", None) is not None:
            return values
        backend_type = values.get("backend_type", None)
        region = values.get("region", None)
        if backend_type is None:
            raise ValueError("backend_type must be specified")
        if region is None:
            raise ValueError("region must be specified")
        values["configuration"] = GatewayConfiguration(
            name=values.get("name", None),
            backend=backend_type,
            region=region,
        )
        return values


class GetGatewayRequest(CoreModel):
    name: str


class DeleteGatewaysRequest(CoreModel):
    names: List[str]


class SetDefaultGatewayRequest(CoreModel):
    name: str


class SetWildcardDomainRequest(CoreModel):
    name: str
    wildcard_domain: str
