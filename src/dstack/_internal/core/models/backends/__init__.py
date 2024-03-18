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
from dstack._internal.core.models.backends.cudo import (
    CudoConfigInfo,
    CudoConfigInfoWithCreds,
    CudoConfigInfoWithCredsPartial,
    CudoConfigValues,
)
from dstack._internal.core.models.backends.datacrunch import (
    DataCrunchConfigInfo,
    DataCrunchConfigInfoWithCreds,
    DataCrunchConfigInfoWithCredsPartial,
    DataCrunchConfigValues,
)
from dstack._internal.core.models.backends.dstack import (
    DstackBaseBackendConfigInfo,
    DstackConfigInfo,
    DstackConfigValues,
)
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
    CudoConfigInfo,
    DataCrunchConfigInfo,
    GCPConfigInfo,
    KubernetesConfigInfo,
    LambdaConfigInfo,
    NebiusConfigInfo,
    TensorDockConfigInfo,
    VastAIConfigInfo,
    DstackConfigInfo,
    DstackBaseBackendConfigInfo,
]
AnyConfigInfoWithCreds = Union[
    AWSConfigInfoWithCreds,
    AzureConfigInfoWithCreds,
    CudoConfigInfoWithCreds,
    DataCrunchConfigInfoWithCreds,
    GCPConfigInfoWithCreds,
    KubernetesConfigInfoWithCreds,
    LambdaConfigInfoWithCreds,
    NebiusConfigInfoWithCreds,
    TensorDockConfigInfoWithCreds,
    VastAIConfigInfoWithCreds,
    DstackConfigInfo,
]
AnyConfigInfoWithCredsPartial = Union[
    AWSConfigInfoWithCredsPartial,
    AzureConfigInfoWithCredsPartial,
    CudoConfigInfoWithCredsPartial,
    DataCrunchConfigInfoWithCredsPartial,
    GCPConfigInfoWithCredsPartial,
    KubernetesConfigInfoWithCredsPartial,
    LambdaConfigInfoWithCredsPartial,
    NebiusConfigInfoWithCredsPartial,
    TensorDockConfigInfoWithCredsPartial,
    VastAIConfigInfoWithCredsPartial,
    DstackConfigInfo,
]
AnyConfigInfo = Union[AnyConfigInfoWithoutCreds, AnyConfigInfoWithCreds]


AnyConfigValues = Union[
    AWSConfigValues,
    AzureConfigValues,
    CudoConfigValues,
    DataCrunchConfigValues,
    GCPConfigValues,
    KubernetesConfigValues,
    LambdaConfigValues,
    NebiusConfigValues,
    TensorDockConfigValues,
    VastAIConfigValues,
    DstackConfigValues,
]


class BackendInfo(BaseModel):
    name: str
    config: AnyConfigInfoWithoutCreds
