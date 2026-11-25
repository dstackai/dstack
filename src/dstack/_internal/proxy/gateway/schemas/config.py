from typing import Optional

from pydantic import AnyHttpUrl, BaseModel

from dstack._internal.proxy.gateway.models import OTelSettings


class ConfigRequest(BaseModel):
    acme_server: Optional[AnyHttpUrl] = None
    acme_eab_kid: Optional[str] = None
    acme_eab_hmac_key: Optional[str] = None
    otel_settings: Optional[OTelSettings] = None
