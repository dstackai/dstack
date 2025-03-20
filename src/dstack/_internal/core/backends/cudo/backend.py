from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.cudo.compute import CudoCompute
from dstack._internal.core.backends.cudo.models import CudoConfig
from dstack._internal.core.models.backends.base import BackendType


class CudoBackend(Backend):
    TYPE = BackendType.CUDO
    COMPUTE_CLASS = CudoCompute

    def __init__(self, config: CudoConfig):
        self.config = config
        self._compute = CudoCompute(self.config)

    def compute(self) -> CudoCompute:
        return self._compute
