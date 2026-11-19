from typing import Optional

from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.metering import BaseProxyMeter
from dstack._internal.proxy.lib.models import Service


class ServerProxyMeter(BaseProxyMeter):
    """Does nothing: tokens are metered on gateways only."""

    def add(
        self,
        caller: ProxyCaller,
        service: Service,
        export_id: Optional[str],
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
    ) -> None:
        pass
