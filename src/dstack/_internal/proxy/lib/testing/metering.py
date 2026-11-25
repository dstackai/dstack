from dataclasses import dataclass
from typing import Optional

from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.metering import BaseProxyMeter
from dstack._internal.proxy.lib.models import Service


@dataclass(frozen=True)
class MeteredTokens:
    caller: ProxyCaller
    service: Service
    export_id: Optional[str]
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class ProxyTestMeter(BaseProxyMeter):
    """Keeps every `add` call in `added`, in order."""

    def __init__(self) -> None:
        self.added: list[MeteredTokens] = []

    def add(
        self,
        caller: ProxyCaller,
        service: Service,
        export_id: Optional[str],
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
    ) -> None:
        self.added.append(
            MeteredTokens(
                caller, service, export_id, input_tokens, cached_input_tokens, output_tokens
            )
        )
