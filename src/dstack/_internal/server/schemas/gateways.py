from typing import Annotated, Any, Dict, List, Optional

from pydantic import Field

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gateways import GatewayConfiguration


class CreateGatewayRequest(CoreModel):
    configuration: GatewayConfiguration
    # Deprecated and unused. Left for compatibility with 0.18 clients.
    name: Annotated[Optional[str], Field(exclude=True)] = None
    backend_type: Annotated[Optional[BackendType], Field(exclude=True)] = None
    region: Annotated[Optional[str], Field(exclude=True)] = None

    class Config:
        @staticmethod
        def schema_extra(schema: Dict[str, Any]) -> None:
            del schema["properties"]["name"]
            del schema["properties"]["backend_type"]
            del schema["properties"]["region"]


class GetGatewayRequest(CoreModel):
    name: str


class DeleteGatewaysRequest(CoreModel):
    names: List[str]


class SetDefaultGatewayRequest(CoreModel):
    name: str


class SetWildcardDomainRequest(CoreModel):
    name: str
    wildcard_domain: str
