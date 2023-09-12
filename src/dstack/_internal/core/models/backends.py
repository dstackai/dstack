import enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Literal


class BackendType(str, enum.Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    LAMBDA = "lambda"


class AWSConfigInfo(BaseModel):
    type: Literal["aws"] = "aws"
    regions: List[str]


class AWSAccessKeyCreds(BaseModel):
    type: Literal["access_key"] = "access_key"
    access_key: str
    secret_key: str


class AWSDefaultCreds(BaseModel):
    type: Literal["default"] = "default"


AnyAWSCreds = Union[AWSAccessKeyCreds, AWSDefaultCreds]


class AWSCreds(BaseModel):
    __root__: AnyAWSCreds = Field(..., discriminator="type")


class AWSConfigInfoWithCreds(AWSConfigInfo):
    creds: AnyAWSCreds


class AWSConfigInfoWithCredsPartial(BaseModel):
    type: Literal["aws"] = "aws"
    creds: Optional[AnyAWSCreds]
    regions: Optional[List[str]]


class GCPConfigInfo(BaseModel):
    type: Literal["gcp"] = "gcp"
    regions: List[str]


class GCPServiceAccountCreds(BaseModel):
    type: Literal["service_account"] = "service_account"
    filename: str
    data: str


class GCPConfigInfoWithCreds(GCPConfigInfo):
    creds: GCPServiceAccountCreds


AnyConfigInfoWithoutCreds = Union[
    AWSConfigInfo,
    GCPConfigInfo,
]


AnyConfigInfoWithCreds = Union[
    AWSConfigInfoWithCreds,
    GCPConfigInfoWithCreds,
]


AnyConfigInfoWithCredsPartial = Union[
    AWSConfigInfoWithCredsPartial,
    None,
]


AnyConfigInfo = Union[AnyConfigInfoWithoutCreds, AnyConfigInfoWithCreds]


class BackendInfo(BaseModel):
    name: str
    config: AnyConfigInfoWithoutCreds


class ConfigElementValue(BaseModel):
    value: str
    label: str


class ConfigMultiElement(BaseModel):
    selected: List[str] = []
    values: List[ConfigElementValue] = []


class AWSConfigValues(BaseModel):
    type: Literal["aws"] = "aws"
    default_creds: bool = False
    regions: Optional[ConfigMultiElement]


AnyConfigValues = Union[AWSConfigValues, None]
