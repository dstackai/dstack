from typing import Dict, Optional

from pydantic import BaseModel
from typing_extensions import Literal


class AWSStorageConfigCredentials(BaseModel):
    access_key: str
    secret_key: str


class AWSStorageConfig(BaseModel):
    bucket: str
    region: str
    credentials: AWSStorageConfigCredentials


class LambdaConfig(BaseModel):
    type: Literal["lambda"] = "lambda"
    api_key: str
    storage_config: AWSStorageConfig
