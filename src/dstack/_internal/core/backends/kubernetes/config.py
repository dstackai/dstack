from typing import Dict

from pydantic import BaseModel

from dstack._internal.core.backends.base.config import BackendConfig


class KubernetesNetworkingConfig(BaseModel):
    ssh_host: str
    ssh_port: int


class KubernetesConfig(BackendConfig):
    kubeconfig: Dict
    networking: KubernetesNetworkingConfig
