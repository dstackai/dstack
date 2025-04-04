from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.nebius.compute import NebiusCompute
from dstack._internal.core.backends.nebius.models import NebiusConfig
from dstack._internal.core.models.backends.base import BackendType


class NebiusBackend(Backend):
    TYPE = BackendType.NEBIUS
    COMPUTE_CLASS = NebiusCompute

    def __init__(self, config: NebiusConfig):
        self.config = config
        self._compute = NebiusCompute(self.config)

    def compute(self) -> NebiusCompute:
        return self._compute
