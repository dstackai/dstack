"""Things stored in GatewayProxyRepo in addition to those from BaseProxyRepo."""

from typing import Optional

from pydantic import AnyHttpUrl, Field

from dstack._internal.proxy.lib.const import DEFAULT_SERVICE_READ_TIMEOUT
from dstack._internal.proxy.lib.models import ImmutableModel
from dstack._internal.proxy.lib.services.usage import MeteringProfile


class ModelEntrypoint(ImmutableModel):
    project_name: str
    domain: str
    https: bool
    read_timeout: int = DEFAULT_SERVICE_READ_TIMEOUT


class ACMESettings(ImmutableModel):
    server: Optional[AnyHttpUrl] = None
    eab_kid: Optional[str] = None
    eab_hmac_key: Optional[str] = None


class GlobalProxyConfig(ImmutableModel):
    acme_settings: ACMESettings = ACMESettings()
    usage_metering_profiles: dict[str, MeteringProfile] = Field(default_factory=dict)
