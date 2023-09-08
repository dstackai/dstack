import enum
from typing import List, Union

from pydantic import BaseModel
from typing_extensions import Literal


class BackendType(str, enum.Enum):
    aws = "aws"
    azure = "azure"
    gcp = "gcp"
    lambdalabs = "lambda"


class AWSConfigInfo(BaseModel):
    type: Literal["aws"] = "aws"
    regions: List[str]


class AWSAccessKeyCreds(BaseModel):
    type: Literal["access_key"] = "access_key"
    access_key: str
    secret_key: str


class AWSConfigInfoWithCreds(AWSConfigInfo):
    creds: AWSAccessKeyCreds


class GCPConfig(BaseModel):
    type: Literal["gcp"] = "gcp"
    regions: List[str]


AnyBackendConfig = Union[
    AWSConfigInfo,
    GCPConfig,
]


class BackendInfo(BaseModel):
    name: str
    config: AnyBackendConfig
