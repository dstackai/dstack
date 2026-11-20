from typing import Optional

from pydantic import AnyHttpUrl, BaseModel

from dstack._internal.proxy.lib.services.usage import MeteringProfile


class ConfigRequest(BaseModel):
    acme_server: Optional[AnyHttpUrl] = None
    acme_eab_kid: Optional[str] = None
    acme_eab_hmac_key: Optional[str] = None
    usage_metering_profiles: Optional[dict[str, MeteringProfile]] = None
