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


class GCPConfigInfo(BaseModel):
    type: Literal["gcp"] = "gcp"
    regions: List[str]


class GCPServiceAccountCreds(BaseModel):
    type: Literal["service_account"] = "service_account"
    filename: str
    data: str


class GCPConfigInfoWithCreds(GCPConfigInfo):
    creds: GCPServiceAccountCreds


AnyBackendConfigWithoutCreds = Union[
    AWSConfigInfo,
    GCPConfigInfo,
]


AnyBackendConfigWithCreds = Union[
    AWSConfigInfoWithCreds,
    GCPConfigInfoWithCreds,
]


AnyBackendConfig = Union[AnyBackendConfigWithoutCreds, AnyBackendConfigWithCreds]


class BackendInfo(BaseModel):
    name: str
    config: AnyBackendConfigWithoutCreds


ConfigValues = ...
