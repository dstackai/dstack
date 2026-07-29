from typing import Annotated, Union

from pydantic import Field

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
    TensorDockBackendConfigWithCreds,
    VastAIBackendConfigWithCreds,
    VultrBackendConfigWithCreds,
    SlurmBackendConfigWithCreds,
    DstackBackendConfig,
]

# Permissive counterpart of `AnyBackendConfigWithCreds` for parsing server responses.
# A newer server may add config fields that an older client's models don't know about;
# parsing with the strict variant would reject the response outright.
#
# Discriminated on `type`: without it, arm selection would depend on trying each of the 20
# arms in order, which only works because every arm happens to declare a `Literal` type.
# `AnyBackendConfigWithCreds` above stays a bare `Union` on purpose. Its two server-side users apply
# `Field(discriminator="type")` at the point of use, which is fine against a bare alias.
# Baking the discriminator into the alias would turn those into doubled `Annotated` `Field`s and
# fail with `ValueError: cannot specify multiple 'Annotated' 'Field's`.
# Discriminating here is because nothing else wraps this alias.
AnyBackendConfigWithCredsResponse = Annotated[
    Union[
        AWSBackendConfigWithCreds.__response__,
        AzureBackendConfigWithCreds.__response__,
        CloudRiftBackendConfigWithCreds.__response__,
        CrusoeBackendConfigWithCreds.__response__,
        CudoBackendConfigWithCreds.__response__,
        VerdaBackendConfigWithCreds.__response__,
        BaseDigitalOceanBackendConfigWithCreds.__response__,
        GCPBackendConfigWithCreds.__response__,
        HotAisleBackendConfigWithCreds.__response__,
        JarvisLabsBackendConfigWithCreds.__response__,
        KubernetesBackendConfigWithCreds.__response__,
        LambdaBackendConfigWithCreds.__response__,
        OCIBackendConfigWithCreds.__response__,
        NebiusBackendConfigWithCreds.__response__,
        RunpodBackendConfigWithCreds.__response__,
        TensorDockBackendConfigWithCreds.__response__,
        VastAIBackendConfigWithCreds.__response__,
        VultrBackendConfigWithCreds.__response__,
        SlurmBackendConfigWithCreds.__response__,
        DstackBackendConfig.__response__,
    ],
    Field(discriminator="type"),
]

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
