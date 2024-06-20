from typing import Union

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
from dstack._internal.core.models.backends.oci import (
    OCIConfigInfo,
    OCIConfigInfoWithCreds,
    OCIConfigInfoWithCredsPartial,
    OCIConfigValues,
)
from dstack._internal.core.models.backends.runpod import (
    RunpodConfigInfo,
    RunpodConfigInfoWithCreds,
    RunpodConfigInfoWithCredsPartial,
    RunpodConfigValues,
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
from dstack._internal.core.models.common import CoreModel

# The following models are the basis of the JSON-based backend API.
# They are also the models used by the Configurator interface.
# The JSON-based backend API is replaced by the YAML-based backend API and not used.
# It's likely to be deprecated and removed.
# Some of the models below like those needed for interactive backend setup could be removed then.
# Still, others are going to stay as Configurator models to keep YAML-based configs and internal configs separated.

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
    DstackConfigInfo,
]

AnyConfigInfo = Union[AnyConfigInfoWithoutCreds, AnyConfigInfoWithCreds]

# Same as AnyConfigInfoWithCreds but some fields may be optional.
# Used for interactive setup with validation and suggestions (e.g. via UI).
# If the backend does not need interactive setup, it's the same as AnyConfigInfoWithCreds.
AnyConfigInfoWithCredsPartial = Union[
    AWSConfigInfoWithCredsPartial,
    AzureConfigInfoWithCredsPartial,
    CudoConfigInfoWithCredsPartial,
    DataCrunchConfigInfoWithCredsPartial,
    GCPConfigInfoWithCredsPartial,
    KubernetesConfigInfoWithCredsPartial,
    LambdaConfigInfoWithCredsPartial,
    NebiusConfigInfoWithCredsPartial,
    OCIConfigInfoWithCredsPartial,
    RunpodConfigInfoWithCredsPartial,
    TensorDockConfigInfoWithCredsPartial,
    VastAIConfigInfoWithCredsPartial,
    DstackConfigInfo,
]

# Suggestions for unfilled fields used in interactive setup.
AnyConfigValues = Union[
    AWSConfigValues,
    AzureConfigValues,
    CudoConfigValues,
    DataCrunchConfigValues,
    GCPConfigValues,
    KubernetesConfigValues,
    LambdaConfigValues,
    NebiusConfigValues,
    OCIConfigValues,
    RunpodConfigValues,
    TensorDockConfigValues,
    VastAIConfigValues,
    DstackConfigValues,
]


# In case we'll support multiple backends of the same type,
# this adds backend name to backend config.
class BackendInfo(CoreModel):
    name: str
    config: AnyConfigInfoWithoutCreds


class BackendInfoYAML(CoreModel):
    name: str
    config_yaml: str
