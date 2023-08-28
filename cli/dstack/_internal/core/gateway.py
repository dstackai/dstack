import time
from typing import List, Optional

from pydantic import BaseModel, Field

from dstack._internal.core.head import BaseHead


class GatewayHead(BaseHead):
    instance_name: str
    external_ip: str
    internal_ip: str
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    region: Optional[str]
    wildcard_domain: Optional[str]

    @classmethod
    def prefix(cls) -> str:
        return "gateways/l;"


class Gateway(BaseModel):
    backend: str
    head: GatewayHead
    default: bool


class GatewayBackend(BaseModel):
    backend: str
    regions: List[str]
