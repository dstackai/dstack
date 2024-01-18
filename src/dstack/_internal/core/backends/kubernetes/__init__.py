import json
import os

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.kubernetes.compute import KubernetesCompute
from dstack._internal.core.backends.kubernetes.config import (
    KubernetesConfig,
    KubernetesNetworkingConfig,
)
from dstack._internal.core.models.backends.base import BackendType


class KubernetesBackend(Backend):
    TYPE: BackendType = BackendType.KUBERNETES

    def __init__(self):
        # self.config = config
        kubeconfig = json.loads(os.environ["DSTACK_KUBECONFIG"])
        config = KubernetesConfig(
            kubeconfig=kubeconfig,
            networking=KubernetesNetworkingConfig(
                ssh_host="localhost",
                ssh_port=32000,
            ),
        )
        self._compute = KubernetesCompute(config)

    def compute(self) -> KubernetesCompute:
        return self._compute
