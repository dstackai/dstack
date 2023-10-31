from typing import Any, Union

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
from dstack._internal.core.models.backends.dstack import DstackConfigInfo, DstackConfigValues
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
from dstack._internal.core.models.backends.tensordock import (
    TensorDockConfigInfo,
    TensorDockConfigInfoWithCreds,
    TensorDockConfigInfoWithCredsPartial,
    TensorDockConfigValues,
)

AnyConfigInfoWithoutCreds = Union[
    AWSConfigInfo,
    AzureConfigInfo,
    GCPConfigInfo,
    LambdaConfigInfo,
    TensorDockConfigInfo,
    DstackConfigInfo,
]
AnyConfigInfoWithCreds = Union[
    AWSConfigInfoWithCreds,
    AzureConfigInfoWithCreds,
    GCPConfigInfoWithCreds,
    LambdaConfigInfoWithCreds,
    TensorDockConfigInfoWithCreds,
    DstackConfigInfo,
]
AnyConfigInfoWithCredsPartial = Union[
    AWSConfigInfoWithCredsPartial,
    AzureConfigInfoWithCredsPartial,
    GCPConfigInfoWithCredsPartial,
    LambdaConfigInfoWithCredsPartial,
    TensorDockConfigInfoWithCredsPartial,
    DstackConfigInfo,
]
AnyConfigInfo = Union[AnyConfigInfoWithoutCreds, AnyConfigInfoWithCreds]


AnyConfigValues = Union[
    AWSConfigValues,
    AzureConfigValues,
    GCPConfigValues,
    LambdaConfigValues,
    TensorDockConfigValues,
    DstackConfigValues,
]


class BackendInfo(BaseModel):
    name: str
    config: AnyConfigInfoWithoutCreds
