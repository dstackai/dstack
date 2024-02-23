from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.cudocompute.compute import CudoComputeCompute
from dstack._internal.core.backends.cudocompute.config import CudoComputeConfig
from dstack._internal.core.models.backends.base import BackendType


class CudoComputeBackend(Backend):
    TYPE: BackendType = BackendType.CUDOCOMPUTE

    def __init__(self, config: CudoComputeConfig):
        self.config = config
        self._compute = CudoComputeCompute(self.config)

    def compute(self) -> CudoComputeCompute:
        return self._compute
