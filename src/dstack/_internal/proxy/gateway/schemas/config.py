from typing import Optional

from pydantic import AnyHttpUrl, BaseModel


class ConfigRequest(BaseModel):
    acme_server: Optional[AnyHttpUrl] = None
    acme_eab_kid: Optional[str] = None
    acme_eab_hmac_key: Optional[str] = None
