from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.crusoe.compute import CrusoeCompute
from dstack._internal.core.backends.crusoe.models import CrusoeConfig
from dstack._internal.core.models.backends.base import BackendType


class CrusoeBackend(Backend):
    TYPE = BackendType.CRUSOE
    COMPUTE_CLASS = CrusoeCompute

    def __init__(self, config: CrusoeConfig):
        self.config = config
        self._compute = CrusoeCompute(self.config)

    def compute(self) -> CrusoeCompute:
        return self._compute
