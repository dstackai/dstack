from typing import Dict, List, Optional

from pydantic import BaseModel, ValidationError
from typing_extensions import Literal

from dstack._internal.backend.base.config import BackendConfig


class AzureConfig(BackendConfig, BaseModel):
    backend: Literal["azure"] = "azure"
    tenant_id: str
    subscription_id: str
    resource_group: str
    storage_account: str
    vault_url: str
    locations: List[str]
    network: Optional[str]
    subnet: Optional[str]
    credentials: Optional[Dict] = None

    def serialize(self) -> Dict:
        return self.dict(exclude={"credentials"})

    @classmethod
    def deserialize(cls, config_data: Dict) -> Optional["AzureConfig"]:
        if config_data.get("backend") != "azure":
            return None
        try:
            return cls.parse_obj(config_data)
        except ValidationError:
            return None
