from typing import Optional, Union

from typing_extensions import Literal

from dstack._internal.core.models.common import CoreModel


class KubernetesNetworkingConfig(CoreModel):
    ssh_host: Optional[str]
    ssh_port: Optional[int]


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
