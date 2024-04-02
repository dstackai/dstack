from pydantic.fields import Field
from typing_extensions import Annotated, Literal, Optional, Union

from dstack._internal.core.models.common import CoreModel


class KubernetesNetworkingConfig(CoreModel):
    ssh_host: Annotated[Optional[str], Field(description="The external IP address of any node")]
    ssh_port: Annotated[
        Optional[str], Field(description="Any port accessible outside of the cluster")
    ]


class KubernetesConfigInfo(CoreModel):
    type: Literal["kubernetes"] = "kubernetes"
    networking: KubernetesNetworkingConfig


class KubeconfigConfig(CoreModel):
    filename: str
    data: str


class KubernetesConfigInfoWithCreds(KubernetesConfigInfo):
    kubeconfig: KubeconfigConfig


AnyKubernetesConfigInfo = Union[KubernetesConfigInfo, KubernetesConfigInfoWithCreds]


class KubernetesConfigInfoWithCredsPartial(KubernetesConfigInfoWithCreds):
    pass


class KubernetesConfigValues(CoreModel):
    type: Literal["kubernetes"] = "kubernetes"


class KubernetesStoredConfig(KubernetesConfigInfoWithCreds):
    pass
