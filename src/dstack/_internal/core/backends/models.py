from typing import Union

from dstack._internal.core.backends.aws.models import (
    AWSBackendConfig,
    AWSBackendConfigWithCreds,
)
from dstack._internal.core.backends.azure.models import (
    AzureBackendConfig,
    AzureBackendConfigWithCreds,
)
from dstack._internal.core.backends.cloudrift.models import (
    CloudRiftBackendConfig,
    CloudRiftBackendConfigWithCreds,
)
from dstack._internal.core.backends.cudo.models import (
    CudoBackendConfig,
    CudoBackendConfigWithCreds,
)
from dstack._internal.core.backends.datacrunch.models import (
    DataCrunchBackendConfig,
    DataCrunchBackendConfigWithCreds,
)
from dstack._internal.core.backends.dstack.models import (
    DstackBackendConfig,
    DstackBaseBackendConfig,
)
from dstack._internal.core.backends.gcp.models import (
    GCPBackendConfig,
    GCPBackendConfigWithCreds,
    GCPBackendFileConfigWithCreds,
)
from dstack._internal.core.backends.hotaisle.models import (
    HotAisleBackendConfig,
    HotAisleBackendConfigWithCreds,
    HotAisleBackendFileConfigWithCreds,
)
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesBackendConfig,
    KubernetesBackendConfigWithCreds,
    KubernetesBackendFileConfigWithCreds,
)
from dstack._internal.core.backends.lambdalabs.models import (
    LambdaBackendConfig,
    LambdaBackendConfigWithCreds,
)
from dstack._internal.core.backends.nebius.models import (
    NebiusBackendConfig,
    NebiusBackendConfigWithCreds,
    NebiusBackendFileConfigWithCreds,
)
from dstack._internal.core.backends.oci.models import (
    OCIBackendConfig,
    OCIBackendConfigWithCreds,
)
from dstack._internal.core.backends.runpod.models import (
    RunpodBackendConfig,
    RunpodBackendConfigWithCreds,
)
from dstack._internal.core.backends.tensordock.models import (
    TensorDockBackendConfig,
    TensorDockBackendConfigWithCreds,
)
from dstack._internal.core.backends.vastai.models import (
    VastAIBackendConfig,
    VastAIBackendConfigWithCreds,
)
from dstack._internal.core.backends.vultr.models import (
    VultrBackendConfig,
    VultrBackendConfigWithCreds,
)
from dstack._internal.core.models.common import CoreModel

# Backend config returned by the API
AnyBackendConfigWithoutCreds = Union[
    AWSBackendConfig,
    AzureBackendConfig,
    CloudRiftBackendConfig,
    CudoBackendConfig,
    DataCrunchBackendConfig,
    GCPBackendConfig,
    HotAisleBackendConfig,
    KubernetesBackendConfig,
    LambdaBackendConfig,
    NebiusBackendConfig,
    OCIBackendConfig,
    RunpodBackendConfig,
    TensorDockBackendConfig,
    VastAIBackendConfig,
    VultrBackendConfig,
    DstackBackendConfig,
    DstackBaseBackendConfig,
]

# Same as AnyBackendConfigWithoutCreds but also includes creds.
# Used to create/update backend.
# Also returned by the API to project admins so that they can see/update backend creds.
AnyBackendConfigWithCreds = Union[
    AWSBackendConfigWithCreds,
    AzureBackendConfigWithCreds,
    CloudRiftBackendConfigWithCreds,
    CudoBackendConfigWithCreds,
    DataCrunchBackendConfigWithCreds,
    GCPBackendConfigWithCreds,
    HotAisleBackendConfigWithCreds,
    KubernetesBackendConfigWithCreds,
    LambdaBackendConfigWithCreds,
    OCIBackendConfigWithCreds,
    NebiusBackendConfigWithCreds,
    RunpodBackendConfigWithCreds,
    TensorDockBackendConfigWithCreds,
    VastAIBackendConfigWithCreds,
    VultrBackendConfigWithCreds,
    DstackBackendConfig,
]

# Backend config accepted in server/config.yaml.
# This can be different from the API config.
# For example, it can make creds data optional and resolve it by filename.
AnyBackendFileConfigWithCreds = Union[
    AWSBackendConfigWithCreds,
    AzureBackendConfigWithCreds,
    CloudRiftBackendConfigWithCreds,
    CudoBackendConfigWithCreds,
    DataCrunchBackendConfigWithCreds,
    GCPBackendFileConfigWithCreds,
    HotAisleBackendFileConfigWithCreds,
    KubernetesBackendFileConfigWithCreds,
    LambdaBackendConfigWithCreds,
    OCIBackendConfigWithCreds,
    NebiusBackendFileConfigWithCreds,
    RunpodBackendConfigWithCreds,
    TensorDockBackendConfigWithCreds,
    VastAIBackendConfigWithCreds,
    VultrBackendConfigWithCreds,
]


# The API can return backend config with or without creds
AnyBackendConfig = Union[AnyBackendConfigWithoutCreds, AnyBackendConfigWithCreds]


# In case we'll support multiple backends of the same type,
# this adds backend name to backend config.
class BackendInfo(CoreModel):
    name: str
    config: AnyBackendConfigWithoutCreds


class BackendInfoYAML(CoreModel):
    name: str
    config_yaml: str
