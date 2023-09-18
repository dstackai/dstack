from typing import Union

from pydantic import BaseModel

from dstack._internal.core.models.backends.aws import (
    AWSConfigInfo,
    AWSConfigInfoWithCreds,
    AWSConfigInfoWithCredsPartial,
    AWSConfigValues,
)
from dstack._internal.core.models.backends.gcp import GCPConfigInfo, GCPConfigInfoWithCreds

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


AnyConfigValues = Union[AWSConfigValues, None]


class BackendInfo(BaseModel):
    name: str
    config: AnyConfigInfoWithoutCreds
