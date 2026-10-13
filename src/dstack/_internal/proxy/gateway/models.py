"""Things stored in GatewayProxyRepo in addition to those from BaseProxyRepo."""

from typing import Optional, Union

from pydantic import AnyHttpUrl

from dstack._internal.proxy.lib.const import DEFAULT_SERVICE_READ_TIMEOUT
from dstack._internal.proxy.lib.models import ImmutableModel


class ModelEntrypoint(ImmutableModel):
    project_name: str
    domain: str
    https: bool
    read_timeout: int = DEFAULT_SERVICE_READ_TIMEOUT


class ACMESettings(ImmutableModel):
    server: Optional[AnyHttpUrl] = None
    eab_kid: Optional[str] = None
    eab_hmac_key: Optional[str] = None


class OTelSettings(ImmutableModel):
    """OpenTelemetry settings of the gateway app, set by the dstack server."""

    traces_enabled: bool = False
    logs_enabled: bool = False
    metrics_enabled: bool = False
    endpoint: Optional[str] = None
    """The OTLP over HTTP base URL, like `OTEL_EXPORTER_OTLP_ENDPOINT`.
    Signal paths such as `/v1/traces` are appended to it."""
    headers: dict[str, str] = {}
    """Headers sent with OTLP requests, e.g. for authorization."""
    traces_sample_rate: float = 1.0
    traces_auth_sample_rate: float = 0.01
    """The head sampling rate for traces of auth subrequests,
    which Nginx makes for every request to services with auth enabled."""
    resource_attributes: dict[str, Union[str, int]] = {}
    """Attributes identifying the gateway replica, such as `service.instance.id`."""

    @property
    def any_enabled(self) -> bool:
        return self.traces_enabled or self.logs_enabled or self.metrics_enabled


class GlobalProxyConfig(ImmutableModel):
    acme_settings: ACMESettings = ACMESettings()
    otel_settings: Optional[OTelSettings] = None
