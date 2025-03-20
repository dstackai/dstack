from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.kubernetes.compute import KubernetesCompute
from dstack._internal.core.backends.kubernetes.models import KubernetesConfig
from dstack._internal.core.models.backends.base import BackendType


class KubernetesBackend(Backend):
    TYPE = BackendType.KUBERNETES
    COMPUTE_CLASS = KubernetesCompute

    def __init__(self, config: KubernetesConfig):
        self.config = config
        self._compute = KubernetesCompute(self.config)

    def compute(self) -> KubernetesCompute:
        return self._compute
