from typing import Literal, Optional

from pydantic import AnyHttpUrl, BaseModel


class ConfigRequest(BaseModel):
    acme_server: Optional[AnyHttpUrl] = None
    acme_eab_kid: Optional[str] = None
    acme_eab_hmac_key: Optional[str] = None
    usage_metering_profiles: Optional[dict[str, Literal["vllm-0.19.1-prompt-details"]]] = None
