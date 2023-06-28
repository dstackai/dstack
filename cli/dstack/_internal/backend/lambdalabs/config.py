from pydantic import BaseModel
from typing_extensions import Literal


class AWSStorageConfigCredentials(BaseModel):
    access_key: str
    secret_key: str


class AWSStorageConfig(BaseModel):
    backend: Literal["aws"] = "aws"
    bucket: str
    region: str
    credentials: AWSStorageConfigCredentials


class LambdaConfig(BaseModel):
    backend: Literal["lambda"] = "lambda"
    api_key: str
    storage_config: AWSStorageConfig
