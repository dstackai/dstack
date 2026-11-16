"""Things stored in GatewayProxyRepo in addition to those from BaseProxyRepo."""

from typing import Literal, Optional

from pydantic import AnyHttpUrl, Field

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


class GlobalProxyConfig(ImmutableModel):
    acme_settings: ACMESettings = ACMESettings()
    usage_metering_profiles: dict[str, Literal["vllm-0.19.1-prompt-details"]] = Field(
        default_factory=dict
    )
