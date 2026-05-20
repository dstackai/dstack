from typing import Annotated, Literal, Optional, Union

from pydantic import Field, root_validator

from dstack._internal.core.backends.base.models import fill_data
from dstack._internal.core.models.common import CoreModel


class KubernetesProxyJumpConfig(CoreModel):
    hostname: Annotated[
        Optional[str], Field(description="The external IP address or hostname of any node")
    ] = None
    port: Annotated[
        Optional[int], Field(description="Any port accessible outside of the cluster")
    ] = None


class KubernetesContextConfig(CoreModel):
    name: Annotated[str, Field(description="The name of the context")]
    proxy_jump: Annotated[
        Optional[KubernetesProxyJumpConfig], Field(description="The SSH proxy jump configuration")
    ] = None


class KubeconfigConfig(CoreModel):
    filename: Annotated[str, Field(description="The path to the kubeconfig file")] = ""
    data: Annotated[str, Field(description="The contents of the kubeconfig file")]


class KubernetesBackendConfig(CoreModel):
    type: Annotated[Literal["kubernetes"], Field(description="The type of backend")] = "kubernetes"
    contexts: Annotated[
        Optional[list[Union[KubernetesContextConfig, str]]],
        Field(
            description=(
                "Enabled contexts (clusters). Each context should map to a separate cluster."
                " The context name becomes the region name."
                " If `contexts` is set, top-level `proxy_jump` and `namespace` must not be set."
                " `proxy_jump`, if necessary, should be configured per-context;"
                " `namespace` is taken from the corresponding kubeconfig context's property."
                " If `contexts` is not set (not recommended), the kubeconfig's `current-context`"
                " is used as the only context, with an empty string as the region name"
            ),
        ),
    ] = None
    proxy_jump: Annotated[
        Optional[KubernetesProxyJumpConfig],
        Field(
            description=(
                "Only used if `contexts` is not set; must not be set otherwise."
                " The SSH proxy jump configuration"
            ),
        ),
    ] = None
    namespace: Annotated[
        Optional[str],
        Field(
            description=(
                "Only used if `contexts` is not set; must not be set otherwise."
                " The namespace for resources managed by `dstack`."
                " If `contexts` is not set, overrides the namespace set in the kubeconfig,"
                " even if not set. Defaults to `default`."
                " Deprecated; will eventually be removed in future versions,"
                " but in the current version must be set if `contexts` is not set and the value"
                " is not equal to `default`."
                " Future versions will use the namespace from the kubeconfig instead."
                " To prepare for future versions, set the same value in the kubeconfig"
            )
        ),
    ] = None
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
