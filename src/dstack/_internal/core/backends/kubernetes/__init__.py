from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.kubernetes.compute import KubernetesCompute
from dstack._internal.core.backends.kubernetes.config import KubernetesConfig
from dstack._internal.core.models.backends.base import BackendType


class KubernetesBackend(Backend):
    TYPE: BackendType = BackendType.KUBERNETES

    def __init__(self, config: KubernetesConfig):
        self.config = config
        self._compute = KubernetesCompute(self.config)

    def compute(self) -> KubernetesCompute:
        return self._compute
