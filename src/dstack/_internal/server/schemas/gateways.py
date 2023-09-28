from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType


class CreateGatewayRequest(BaseModel):
    name: Optional[str]
    backend_type: BackendType
    region: str


class GetGatewayRequest(BaseModel):
    name: str


class DeleteGatewaysRequest(BaseModel):
    names: List[str]


class SetDefaultGatewayRequest(BaseModel):
    name: str


class SetWildcardDomainRequest(BaseModel):
    name: str
    wildcard_domain: str
