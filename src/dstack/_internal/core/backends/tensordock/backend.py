from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.tensordock.compute import TensorDockCompute
from dstack._internal.core.backends.tensordock.models import TensorDockConfig
from dstack._internal.core.models.backends.base import BackendType


class TensorDockBackend(Backend):
    TYPE = BackendType.TENSORDOCK
    COMPUTE_CLASS = TensorDockCompute

    def __init__(self, config: TensorDockConfig):
        self.config = config
        self._compute = TensorDockCompute(self.config)

    def compute(self) -> TensorDockCompute:
        return self._compute
