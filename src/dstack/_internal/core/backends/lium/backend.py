from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.lium.compute import LiumCompute
from dstack._internal.core.backends.lium.models import LiumConfig
from dstack._internal.core.models.backends.base import BackendType


class LiumBackend(Backend):
    TYPE = BackendType.LIUM
    COMPUTE_CLASS = LiumCompute

    def __init__(self, config: LiumConfig):
        self.config = config
        self._compute = LiumCompute(self.config)

    def compute(self) -> LiumCompute:
        return self._compute
