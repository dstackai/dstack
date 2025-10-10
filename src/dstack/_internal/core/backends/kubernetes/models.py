from typing import Annotated, Literal, Optional, Union

import yaml
from pydantic import Field, root_validator, validator

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
    data: Annotated[dict, Field(description="The contents of the kubeconfig file")]

    @validator("data", pre=True)
    def convert_data(cls, v: Union[str, dict]) -> dict:
        if isinstance(v, dict):
            return v
        return yaml.load(v, yaml.FullLoader)


class KubernetesBackendConfig(CoreModel):
    type: Annotated[Literal["kubernetes"], Field(description="The type of backend")] = "kubernetes"
    proxy_jump: Annotated[
        Optional[KubernetesProxyJumpConfig], Field(description="The SSH proxy jump configuration")
    ] = None
    namespace: Annotated[
        str, Field(description="The namespace for resources managed by `dstack`")
    ] = DEFAULT_NAMESPACE


class KubernetesBackendConfigWithCreds(KubernetesBackendConfig):
    kubeconfig: Annotated[KubeconfigConfig, Field(description="The kubeconfig configuration")]


class KubeconfigFileConfig(CoreModel):
    filename: Annotated[str, Field(description="The path to the kubeconfig file")]
    data: Annotated[
        # str data converted to dict when parsed as KubeconfigConfig
        Optional[Union[str, dict]],
        Field(
            description=(
                "The contents of the kubeconfig file specified as yaml or a string."
                " When configuring via `server/config.yml`, it's automatically filled from `filename`."
                " When configuring via UI, it has to be specified explicitly"
            )
        ),
    ] = None

    @root_validator
    def fill_data(cls, values):
        return fill_data(values)


class KubernetesBackendFileConfigWithCreds(KubernetesBackendConfig):
    kubeconfig: Annotated[KubeconfigFileConfig, Field(description="The kubeconfig configuration")]


AnyKubernetesBackendConfig = Union[KubernetesBackendConfig, KubernetesBackendConfigWithCreds]


class KubernetesStoredConfig(KubernetesBackendConfigWithCreds):
    pass


class KubernetesConfig(KubernetesStoredConfig):
    pass
