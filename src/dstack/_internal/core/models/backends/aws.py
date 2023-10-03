from typing import List, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement


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


AnyAWSConfigInfo = Union[AWSConfigInfo, AWSConfigInfoWithCreds]


class AWSConfigInfoWithCredsPartial(BaseModel):
    type: Literal["aws"] = "aws"
    creds: Optional[AnyAWSCreds]
    regions: Optional[List[str]]


class AWSConfigValues(BaseModel):
    type: Literal["aws"] = "aws"
    default_creds: bool = False
    regions: Optional[ConfigMultiElement]


class AWSStoredConfig(AWSConfigInfo):
    pass
