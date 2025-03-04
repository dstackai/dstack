from typing import Union

from dstack._internal.core.models.backends.aws import (
    AWSConfigInfo,
    AWSConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.azure import (
    AzureConfigInfo,
    AzureConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.cudo import (
    CudoConfigInfo,
    CudoConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.datacrunch import (
    DataCrunchConfigInfo,
    DataCrunchConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.dstack import (
    DstackBaseBackendConfigInfo,
    DstackConfigInfo,
)
from dstack._internal.core.models.backends.gcp import (
    GCPConfigInfo,
    GCPConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.kubernetes import (
    KubernetesConfigInfo,
    KubernetesConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.lambdalabs import (
    LambdaConfigInfo,
    LambdaConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.nebius import (
    NebiusConfigInfo,
    NebiusConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.oci import (
    OCIConfigInfo,
    OCIConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.runpod import (
    RunpodConfigInfo,
    RunpodConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.tensordock import (
    TensorDockConfigInfo,
    TensorDockConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.vastai import (
    VastAIConfigInfo,
    VastAIConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.vultr import (
    VultrConfigInfo,
    VultrConfigInfoWithCreds,
)
from dstack._internal.core.models.common import CoreModel

# The following models are the basis of the JSON-based backend API.
# They are also the models used by the Configurator interface.
# The JSON-based backend API is replaced by the YAML-based backend API and not used.
# It's likely to be deprecated and removed.

# Backend config returned by the API
AnyConfigInfoWithoutCreds = Union[
    AWSConfigInfo,
    AzureConfigInfo,
    CudoConfigInfo,
    DataCrunchConfigInfo,
    GCPConfigInfo,
    KubernetesConfigInfo,
    LambdaConfigInfo,
    NebiusConfigInfo,
    OCIConfigInfo,
    RunpodConfigInfo,
    TensorDockConfigInfo,
    VastAIConfigInfo,
    VultrConfigInfo,
    DstackConfigInfo,
    DstackBaseBackendConfigInfo,
]

# Same as AnyConfigInfoWithoutCreds but also includes creds.
# Used to create/update backend.
# Also returned by the API to project admins so that they can see/update backend creds.
AnyConfigInfoWithCreds = Union[
    AWSConfigInfoWithCreds,
    AzureConfigInfoWithCreds,
    CudoConfigInfoWithCreds,
    DataCrunchConfigInfoWithCreds,
    GCPConfigInfoWithCreds,
    KubernetesConfigInfoWithCreds,
    LambdaConfigInfoWithCreds,
    NebiusConfigInfoWithCreds,
    OCIConfigInfoWithCreds,
    RunpodConfigInfoWithCreds,
    TensorDockConfigInfoWithCreds,
    VastAIConfigInfoWithCreds,
    VultrConfigInfoWithCreds,
    DstackConfigInfo,
]

AnyConfigInfo = Union[AnyConfigInfoWithoutCreds, AnyConfigInfoWithCreds]


# In case we'll support multiple backends of the same type,
# this adds backend name to backend config.
class BackendInfo(CoreModel):
    name: str
    config: AnyConfigInfoWithoutCreds


class BackendInfoYAML(CoreModel):
    name: str
    config_yaml: str
