from dataclasses import dataclass
from typing import Any, Union
from unittest.mock import AsyncMock, MagicMock

from dstack._internal.proxy.gateway.models import OTelSettings

AnyMock = Union[MagicMock, AsyncMock]


@dataclass
class Mocks:
    reload_nginx: AnyMock
    run_certbot: AnyMock
    open_conn: AnyMock
    close_conn: AnyMock


def make_otel_settings(**kwargs: Any) -> OTelSettings:
    defaults: dict[str, Any] = {
        "traces_enabled": False,
        "logs_enabled": False,
        "metrics_enabled": False,
        "endpoint": "https://otlp.example.com",
        "headers": {},
        "traces_sample_rate": 1.0,
        "traces_auth_sample_rate": 0.01,
        "resource_attributes": {},
    }
    return OTelSettings(**{**defaults, **kwargs})
