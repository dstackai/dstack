from typing import Annotated, Literal, Optional, Union

from pydantic import Field, root_validator

from dstack._internal.core.backends.base.models import fill_data
from dstack._internal.core.models.common import CoreModel

DEFAULT_NAMESPACE = "default"


class KubernetesProxyJumpConfig(CoreModel):
    hostname: Annotated[
        Optional[str], Field(description="The external IP address or hostname of any node")
    ] = None
    port: Annotated[
        Optional[int], Field(description="Any port accessible outside of the cluster")
    ] = None


class KubeconfigConfig(CoreModel):
    filename: Annotated[str, Field(description="The path to the kubeconfig file")] = ""
    data: Annotated[str, Field(description="The contents of the kubeconfig file")]


class KubernetesBackendConfig(CoreModel):
    type: Annotated[Literal["kubernetes"], Field(description="The type of backend")] = "kubernetes"
    proxy_jump: Annotated[
        Optional[KubernetesProxyJumpConfig], Field(description="The SSH proxy jump configuration")
    ] = None
    namespace: Annotated[
        str,
        Field(
            description=(
                "The namespace for resources managed by `dstack`."
                " Always overrides the namespace set in the kubeconfig, even if not set. "
                " Deprecated and will be eventually removed in futute versions, but"
                " in the current version must be set unless equals to `default`."
                " Future versions will use the namespace from the kubeconfig instead."
                " To prepare for future versions, set the same value in the kubeconfig"
            )
        ),
    ] = DEFAULT_NAMESPACE
    """`namespace` is formally deprecated since 0.20.20 but still used. Future versions will switch
    to namespace from kubeconfig context, which is currently ignored"""


class KubernetesBackendConfigWithCreds(KubernetesBackendConfig):
    kubeconfig: Annotated[KubeconfigConfig, Field(description="The kubeconfig configuration")]


class KubeconfigFileConfig(CoreModel):
    filename: Annotated[str, Field(description="The path to the kubeconfig file")] = ""
    data: Annotated[
        Optional[str],
        Field(
            description=(
                "The contents of the kubeconfig file."
                " When configuring via `server/config.yml`, it's automatically filled from `filename`."
                " When configuring via UI, it has to be specified explicitly"
            )
        ),
    ] = None

    @root_validator
    def fill_data(cls, values: dict) -> dict:
        if values.get("filename") == "" and values.get("data") is None:
            raise ValueError("filename or data must be specified")
        return fill_data(values)


class KubernetesBackendFileConfigWithCreds(KubernetesBackendConfig):
    kubeconfig: Annotated[KubeconfigFileConfig, Field(description="The kubeconfig configuration")]


AnyKubernetesBackendConfig = Union[KubernetesBackendConfig, KubernetesBackendConfigWithCreds]


class KubernetesStoredConfig(KubernetesBackendConfigWithCreds):
    pass


class KubernetesConfig(KubernetesStoredConfig):
    pass
