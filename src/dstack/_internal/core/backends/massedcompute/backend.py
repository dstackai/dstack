from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.massedcompute.compute import MassedComputeCompute
from dstack._internal.core.backends.massedcompute.models import MassedComputeConfig
from dstack._internal.core.models.backends.base import BackendType


class MassedComputeBackend(Backend):
    TYPE = BackendType.MASSEDCOMPUTE
    COMPUTE_CLASS = MassedComputeCompute

    def __init__(self, config: MassedComputeConfig):
        self.config = config
        self._compute = MassedComputeCompute(self.config)

    def compute(self) -> MassedComputeCompute:
        return self._compute
