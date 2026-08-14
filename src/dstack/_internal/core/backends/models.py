from typing import Annotated, Union

from pydantic import Field, RootModel

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
from dstack._internal.core.backends.crusoe.models import (
    CrusoeBackendConfig,
    CrusoeBackendConfigWithCreds,
    CrusoeBackendFileConfigWithCreds,
)
from dstack._internal.core.backends.cudo.models import (
    CudoBackendConfig,
    CudoBackendConfigWithCreds,
)
from dstack._internal.core.backends.digitalocean_base.models import (
    BaseDigitalOceanBackendConfig,
    BaseDigitalOceanBackendConfigWithCreds,
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
from dstack._internal.core.backends.jarvislabs.models import (
    JarvisLabsBackendConfig,
    JarvisLabsBackendConfigWithCreds,
    JarvisLabsBackendFileConfigWithCreds,
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
from dstack._internal.core.backends.seeweb.models import (
    SeewebBackendConfig,
    SeewebBackendConfigWithCreds,
)
from dstack._internal.core.backends.slurm.models import (
    SlurmBackendConfig,
    SlurmBackendConfigWithCreds,
    SlurmBackendFileConfigWithCreds,
)
from dstack._internal.core.backends.tensordock.models import (
    TensorDockBackendConfig,
    TensorDockBackendConfigWithCreds,
)
from dstack._internal.core.backends.vastai.models import (
    VastAIBackendConfig,
    VastAIBackendConfigWithCreds,
)
from dstack._internal.core.backends.verda.models import (
    VerdaBackendConfig,
    VerdaBackendConfigWithCreds,
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
    CrusoeBackendConfig,
    CudoBackendConfig,
    BaseDigitalOceanBackendConfig,
    GCPBackendConfig,
    HotAisleBackendConfig,
    JarvisLabsBackendConfig,
    KubernetesBackendConfig,
    LambdaBackendConfig,
    NebiusBackendConfig,
    OCIBackendConfig,
    RunpodBackendConfig,
    SeewebBackendConfig,
    TensorDockBackendConfig,
    VastAIBackendConfig,
    VerdaBackendConfig,
    VultrBackendConfig,
    SlurmBackendConfig,
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
    CrusoeBackendConfigWithCreds,
    CudoBackendConfigWithCreds,
    VerdaBackendConfigWithCreds,
    BaseDigitalOceanBackendConfigWithCreds,
    GCPBackendConfigWithCreds,
    HotAisleBackendConfigWithCreds,
    JarvisLabsBackendConfigWithCreds,
    KubernetesBackendConfigWithCreds,
    LambdaBackendConfigWithCreds,
    OCIBackendConfigWithCreds,
    NebiusBackendConfigWithCreds,
    RunpodBackendConfigWithCreds,
    SeewebBackendConfigWithCreds,
    TensorDockBackendConfigWithCreds,
    VastAIBackendConfigWithCreds,
    VultrBackendConfigWithCreds,
    SlurmBackendConfigWithCreds,
    DstackBackendConfig,
]

# The same union tagged for validation. Without the discriminator, arm selection would depend on
# trying each of the 20 arms in order and reporting 20 errors when none match.
#
# `AnyBackendConfigWithCreds` above stays a bare `Union` because it is also used as a plain type
# annotation and as the bound of `BackendConfigWithCredsT` in `base/configurator.py`. Every site
# that *validates* the union should use this alias instead of wrapping it again locally: two
# `Annotated` `Field`s on the same type fail with "cannot specify multiple 'Annotated' 'Field's".
AnyBackendConfigWithCredsTagged = Annotated[
    AnyBackendConfigWithCreds,
    Field(discriminator="type"),
]


class BackendConfigWithCreds(RootModel[AnyBackendConfigWithCredsTagged]):
    pass


# Backend config accepted in server/config.yaml.
# This can be different from the API config.
# For example, it can make creds data optional and resolve it by filename.
AnyBackendFileConfigWithCreds = Union[
    AWSBackendConfigWithCreds,
    AzureBackendConfigWithCreds,
    CloudRiftBackendConfigWithCreds,
    CrusoeBackendFileConfigWithCreds,
    CudoBackendConfigWithCreds,
    VerdaBackendConfigWithCreds,
    BaseDigitalOceanBackendConfigWithCreds,
    GCPBackendFileConfigWithCreds,
    HotAisleBackendFileConfigWithCreds,
    JarvisLabsBackendFileConfigWithCreds,
    KubernetesBackendFileConfigWithCreds,
    LambdaBackendConfigWithCreds,
    OCIBackendConfigWithCreds,
    NebiusBackendFileConfigWithCreds,
    RunpodBackendConfigWithCreds,
    SeewebBackendConfigWithCreds,
    TensorDockBackendConfigWithCreds,
    VastAIBackendConfigWithCreds,
    VultrBackendConfigWithCreds,
    SlurmBackendFileConfigWithCreds,
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
