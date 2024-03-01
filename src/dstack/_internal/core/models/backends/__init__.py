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
from dstack._internal.core.models.backends.cudocompute import (
    CudoComputeConfigInfo,
    CudoComputeConfigInfoWithCreds,
    CudoComputeConfigInfoWithCredsPartial,
    CudoComputeConfigValues,
)
from dstack._internal.core.models.backends.datacrunch import (
    DataCrunchConfigInfo,
    DataCrunchConfigInfoWithCreds,
    DataCrunchConfigInfoWithCredsPartial,
    DataCrunchConfigValues,
)
from dstack._internal.core.models.backends.dstack import DstackConfigInfo, DstackConfigValues
from dstack._internal.core.models.backends.gcp import (
    GCPConfigInfo,
    GCPConfigInfoWithCreds,
    GCPConfigInfoWithCredsPartial,
    GCPConfigValues,
)
from dstack._internal.core.models.backends.kubernetes import (
    KubernetesConfigInfo,
    KubernetesConfigInfoWithCreds,
    KubernetesConfigInfoWithCredsPartial,
    KubernetesConfigValues,
)
from dstack._internal.core.models.backends.lambdalabs import (
    LambdaConfigInfo,
    LambdaConfigInfoWithCreds,
    LambdaConfigInfoWithCredsPartial,
    LambdaConfigValues,
)
from dstack._internal.core.models.backends.nebius import (
    NebiusConfigInfo,
    NebiusConfigInfoWithCreds,
    NebiusConfigInfoWithCredsPartial,
    NebiusConfigValues,
)
from dstack._internal.core.models.backends.tensordock import (
    TensorDockConfigInfo,
    TensorDockConfigInfoWithCreds,
    TensorDockConfigInfoWithCredsPartial,
    TensorDockConfigValues,
)
from dstack._internal.core.models.backends.vastai import (
    VastAIConfigInfo,
    VastAIConfigInfoWithCreds,
    VastAIConfigInfoWithCredsPartial,
    VastAIConfigValues,
)

AnyConfigInfoWithoutCreds = Union[
    AWSConfigInfo,
    AzureConfigInfo,
    DataCrunchConfigInfo,
    GCPConfigInfo,
    KubernetesConfigInfo,
    LambdaConfigInfo,
    NebiusConfigInfo,
    TensorDockConfigInfo,
    VastAIConfigInfo,
    DstackConfigInfo,
    CudoComputeConfigInfo,
]
AnyConfigInfoWithCreds = Union[
    AWSConfigInfoWithCreds,
    AzureConfigInfoWithCreds,
    DataCrunchConfigInfoWithCreds,
    GCPConfigInfoWithCreds,
    KubernetesConfigInfoWithCreds,
    LambdaConfigInfoWithCreds,
    NebiusConfigInfoWithCreds,
    TensorDockConfigInfoWithCreds,
    VastAIConfigInfoWithCreds,
    DstackConfigInfo,
    CudoComputeConfigInfoWithCreds,
]
AnyConfigInfoWithCredsPartial = Union[
    AWSConfigInfoWithCredsPartial,
    AzureConfigInfoWithCredsPartial,
    DataCrunchConfigInfoWithCredsPartial,
    GCPConfigInfoWithCredsPartial,
    KubernetesConfigInfoWithCredsPartial,
    LambdaConfigInfoWithCredsPartial,
    NebiusConfigInfoWithCredsPartial,
    TensorDockConfigInfoWithCredsPartial,
    VastAIConfigInfoWithCredsPartial,
    DstackConfigInfo,
    CudoComputeConfigInfoWithCredsPartial,
]
AnyConfigInfo = Union[AnyConfigInfoWithoutCreds, AnyConfigInfoWithCreds]


AnyConfigValues = Union[
    AWSConfigValues,
    AzureConfigValues,
    DataCrunchConfigValues,
    GCPConfigValues,
    KubernetesConfigValues,
    LambdaConfigValues,
    NebiusConfigValues,
    TensorDockConfigValues,
    VastAIConfigValues,
    DstackConfigValues,
    CudoComputeConfigValues,
]


class BackendInfo(BaseModel):
    name: str
    config: AnyConfigInfoWithoutCreds
