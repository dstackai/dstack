from typing import Optional, Union

from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.common import ForbidExtra


class KubernetesNetworkingConfig(ForbidExtra):
    ssh_host: Optional[str]
    ssh_port: Optional[int]


class KubernetesConfigInfo(BaseModel):
    type: Literal["kubernetes"] = "kubernetes"
    networking: KubernetesNetworkingConfig


class KubeconfigConfig(ForbidExtra):
    filename: str
    data: str


class KubernetesConfigInfoWithCreds(KubernetesConfigInfo):
    kubeconfig: KubeconfigConfig


AnyKubernetesConfigInfo = Union[KubernetesConfigInfo, KubernetesConfigInfoWithCreds]


class KubernetesConfigInfoWithCredsPartial(KubernetesConfigInfoWithCreds):
    pass


class KubernetesConfigValues(BaseModel):
    type: Literal["kubernetes"] = "kubernetes"


class KubernetesStoredConfig(KubernetesConfigInfoWithCreds):
    pass
