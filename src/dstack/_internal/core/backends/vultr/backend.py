from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.vultr.compute import VultrCompute
from dstack._internal.core.backends.vultr.models import VultrConfig
from dstack._internal.core.models.backends.base import BackendType


class VultrBackend(Backend):
    TYPE = BackendType.VULTR
    COMPUTE_CLASS = VultrCompute

    def __init__(self, config: VultrConfig):
        self.config = config
        self._compute = VultrCompute(self.config)

    def compute(self) -> VultrCompute:
        return self._compute
