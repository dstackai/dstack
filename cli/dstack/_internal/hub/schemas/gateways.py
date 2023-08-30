from typing import List, Optional, Union

from pydantic import BaseModel, constr
from typing_extensions import Literal

WildcardDomain = constr(strip_whitespace=True, regex=r"^\*\.(.+)$")


class GatewayDelete(BaseModel):
    instance_names: List[str]


class GatewayCreate(BaseModel):
    backend: str
    region: str


class GatewayUpdate(BaseModel):
    wildcard_domain: Optional[Union[WildcardDomain, Literal[""]]]
    default: Optional[bool]


class GatewayTestDomain(BaseModel):
    domain: WildcardDomain
