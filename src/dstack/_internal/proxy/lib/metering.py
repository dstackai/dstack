from abc import ABC, abstractmethod
from typing import Optional

from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.models import Service


class BaseProxyMeter(ABC):
    """Meters the tokens of requests to models."""

    @abstractmethod
    def add(
        self,
        caller: ProxyCaller,
        service: Service,
        export_id: Optional[str],
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
    ) -> None:
        """
        Adds tokens newly counted for the caller's request to the service.
        `export_id` is the export that the request came through,
        `None` for a request to the project's own model.
        `input_tokens` includes `cached_input_tokens`.
        """
        pass
