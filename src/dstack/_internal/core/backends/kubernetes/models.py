from typing import Annotated, Literal, Optional, Union

from pydantic import Field, root_validator

from dstack._internal.core.backends.base.models import fill_data
from dstack._internal.core.models.common import CoreModel


class KubernetesNetworkingConfig(CoreModel):
    ssh_host: Annotated[
        Optional[str], Field(description="The external IP address of any node")
    ] = None
    ssh_port: Annotated[
        Optional[int], Field(description="Any port accessible outside of the cluster")
    ] = None


class KubeconfigConfig(CoreModel):
    filename: Annotated[str, Field(description="The path to the kubeconfig file")] = ""
    data: Annotated[str, Field(description="The contents of the kubeconfig file")]


class KubernetesBackendConfig(CoreModel):
    type: Annotated[Literal["kubernetes"], Field(description="The type of backend")] = "kubernetes"
    networking: Annotated[
        Optional[KubernetesNetworkingConfig], Field(description="The networking configuration")
    ] = None


class KubernetesBackendConfigWithCreds(CoreModel):
    type: Annotated[Literal["kubernetes"], Field(description="The type of backend")] = "kubernetes"
    networking: Annotated[
        Optional[KubernetesNetworkingConfig], Field(description="The networking configuration")
    ] = None
    kubeconfig: Annotated[KubeconfigConfig, Field(description="The kubeconfig configuration")]


class KubeconfigFileConfig(CoreModel):
    filename: Annotated[str, Field(description="The path to the kubeconfig file")]
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
    def fill_data(cls, values):
        return fill_data(values)


class KubernetesBackendFileConfigWithCreds(CoreModel):
    type: Annotated[Literal["kubernetes"], Field(description="The type of backend")] = "kubernetes"
    networking: Annotated[
        Optional[KubernetesNetworkingConfig], Field(description="The networking configuration")
    ] = None
    kubeconfig: Annotated[KubeconfigFileConfig, Field(description="The kubeconfig configuration")]


AnyKubernetesBackendConfig = Union[KubernetesBackendConfig, KubernetesBackendConfigWithCreds]


class KubernetesStoredConfig(KubernetesBackendConfigWithCreds):
    pass


class KubernetesConfig(KubernetesStoredConfig):
    pass
