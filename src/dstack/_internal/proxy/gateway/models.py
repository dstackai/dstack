"""Things stored in GatewayProxyRepo in addition to those from BaseProxyRepo."""

from typing import Optional

from pydantic import AnyHttpUrl

from dstack._internal.proxy.lib.models import ImmutableModel


class ModelEntrypoint(ImmutableModel):
    project_name: str
    domain: str
    https: bool


class ACMESettings(ImmutableModel):
    server: Optional[AnyHttpUrl] = None
    eab_kid: Optional[str] = None
    eab_hmac_key: Optional[str] = None


class GlobalProxyConfig(ImmutableModel):
    acme_settings: ACMESettings = ACMESettings()
