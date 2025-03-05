from typing import Union

from dstack._internal.core.backends.aws.models import (
    AWSConfigInfo,
    AWSConfigInfoWithCreds,
)
from dstack._internal.core.backends.azure.models import (
    AzureConfigInfo,
    AzureConfigInfoWithCreds,
)
from dstack._internal.core.backends.cudo.models import (
    CudoConfigInfo,
    CudoConfigInfoWithCreds,
)
from dstack._internal.core.backends.datacrunch.models import (
    DataCrunchConfigInfo,
    DataCrunchConfigInfoWithCreds,
)
from dstack._internal.core.backends.dstack.models import (
    DstackBaseBackendConfigInfo,
    DstackConfigInfo,
)
from dstack._internal.core.backends.gcp.models import (
    GCPConfigInfo,
    GCPConfigInfoWithCreds,
)
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesConfigInfo,
    KubernetesConfigInfoWithCreds,
)
from dstack._internal.core.backends.lambdalabs.models import (
    LambdaConfigInfo,
    LambdaConfigInfoWithCreds,
)
from dstack._internal.core.backends.nebius.models import (
    NebiusConfigInfo,
    NebiusConfigInfoWithCreds,
)
from dstack._internal.core.backends.oci.models import (
    OCIConfigInfo,
    OCIConfigInfoWithCreds,
)
from dstack._internal.core.backends.runpod.models import (
    RunpodConfigInfo,
    RunpodConfigInfoWithCreds,
)
from dstack._internal.core.backends.tensordock.models import (
    TensorDockConfigInfo,
    TensorDockConfigInfoWithCreds,
)
from dstack._internal.core.backends.vastai.models import (
    VastAIConfigInfo,
    VastAIConfigInfoWithCreds,
)
from dstack._internal.core.backends.vultr.models import (
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
