import time

from pydantic import Field

from dstack._internal.core.head import BaseHead


class GatewayHead(BaseHead):
    instance_name: str
    external_ip: str
    internal_ip: str
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))

    @classmethod
    def prefix(cls) -> str:
        return "gateways/l;"
