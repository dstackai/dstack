from typing import Dict

from pydantic import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class AWSConfigInfo(CoreModel):
    type: Literal["aws"] = "aws"
    regions: Optional[List[str]] = None
    vpc_name: Optional[str] = None
    vpc_ids: Optional[Dict[str, str]] = None
    default_vpcs: Optional[bool] = None
    public_ips: Optional[bool] = None


class AWSAccessKeyCreds(CoreModel):
    type: Annotated[Literal["access_key"], Field(description="The type of credentials")] = (
        "access_key"
    )
    access_key: Annotated[str, Field(description="The access key")]
    secret_key: Annotated[str, Field(description="The secret key")]


class AWSDefaultCreds(CoreModel):
    type: Annotated[Literal["default"], Field(description="The type of credentials")] = "default"


AnyAWSCreds = Union[AWSAccessKeyCreds, AWSDefaultCreds]


class AWSCreds(CoreModel):
    __root__: AnyAWSCreds = Field(..., discriminator="type")


class AWSConfigInfoWithCreds(AWSConfigInfo):
    creds: AnyAWSCreds


AnyAWSConfigInfo = Union[AWSConfigInfo, AWSConfigInfoWithCreds]


class AWSConfigInfoWithCredsPartial(CoreModel):
    type: Literal["aws"] = "aws"
    creds: Optional[AnyAWSCreds]
    regions: Optional[List[str]]
    vpc_name: Optional[str]
    vpc_ids: Optional[Dict[str, str]]
    default_vpcs: Optional[bool]
    public_ips: Optional[bool]


class AWSConfigValues(CoreModel):
    type: Literal["aws"] = "aws"
    default_creds: bool = False
    regions: Optional[ConfigMultiElement]


class AWSStoredConfig(AWSConfigInfo):
    pass
