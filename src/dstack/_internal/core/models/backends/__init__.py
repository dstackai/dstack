from typing import Union

from pydantic import BaseModel

from dstack._internal.core.models.backends.aws import (
    AWSConfigInfo,
    AWSConfigInfoWithCreds,
    AWSConfigInfoWithCredsPartial,
    AWSConfigValues,
)
from dstack._internal.core.models.backends.azure import (
    AzureConfigInfo,
    AzureConfigInfoWithCreds,
    AzureConfigInfoWithCredsPartial,
    AzureConfigValues,
)
from dstack._internal.core.models.backends.gcp import (
    GCPConfigInfo,
    GCPConfigInfoWithCreds,
    GCPConfigInfoWithCredsPartial,
    GCPConfigValues,
)
from dstack._internal.core.models.backends.lambdalabs import (
    LambdaConfigInfo,
    LambdaConfigInfoWithCreds,
    LambdaConfigInfoWithCredsPartial,
    LambdaConfigValues,
)

AnyConfigInfoWithoutCreds = Union[
    AWSConfigInfo,
    AzureConfigInfo,
    GCPConfigInfo,
    LambdaConfigInfo,
]
AnyConfigInfoWithCreds = Union[
    AWSConfigInfoWithCreds,
    AzureConfigInfoWithCreds,
    GCPConfigInfoWithCreds,
    LambdaConfigInfoWithCreds,
]
AnyConfigInfoWithCredsPartial = Union[
    AWSConfigInfoWithCredsPartial,
    AzureConfigInfoWithCredsPartial,
    GCPConfigInfoWithCredsPartial,
    LambdaConfigInfoWithCredsPartial,
]
AnyConfigInfo = Union[AnyConfigInfoWithoutCreds, AnyConfigInfoWithCreds]


AnyConfigValues = Union[
    AWSConfigValues,
    AzureConfigValues,
    GCPConfigValues,
    LambdaConfigValues,
]


class BackendInfo(BaseModel):
    name: str
    config: AnyConfigInfoWithoutCreds
