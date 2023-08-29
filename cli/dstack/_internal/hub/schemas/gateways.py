from typing import List, Optional

from pydantic import BaseModel, constr

WildcardDomain = constr(strip_whitespace=True, regex=r"^\*\.(.+)$")


class GatewayDelete(BaseModel):
    instance_names: List[str]


class GatewayCreate(BaseModel):
    backend: str
    region: str


class GatewayUpdate(BaseModel):
    wildcard_domain: Optional[WildcardDomain]
    default: Optional[bool]


class GatewayTestDomain(BaseModel):
    domain: WildcardDomain
