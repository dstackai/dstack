from typing import Optional

from pydantic import AnyHttpUrl, BaseModel


class ConfigRequest(BaseModel):
    acme_server: Optional[AnyHttpUrl]
    acme_eab_kid: Optional[str]
    acme_eab_hmac_key: Optional[str]
