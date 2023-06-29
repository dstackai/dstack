from typing import Dict, List, Optional

from pydantic import BaseModel, ValidationError
from typing_extensions import Literal

from dstack._internal.backend.base.config import BackendConfig


class AWSStorageConfigCredentials(BaseModel):
    access_key: str
    secret_key: str


class AWSStorageConfig(BaseModel):
    backend: Literal["aws"] = "aws"
    bucket: str
    region: str
    credentials: AWSStorageConfigCredentials


class LambdaConfig(BackendConfig, BaseModel):
    backend: Literal["lambda"] = "lambda"
    regions: List[str]
    api_key: str
    storage_config: AWSStorageConfig

    def serialize(self) -> Dict:
        return self.dict()

    @classmethod
    def deserialize(cls, config_data: Dict) -> Optional["LambdaConfig"]:
        try:
            return LambdaConfig.parse_obj(config_data)
        except ValidationError:
            return None
