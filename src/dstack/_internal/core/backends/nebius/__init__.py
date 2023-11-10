from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.nebius.compute import NebiusCompute
from dstack._internal.core.backends.nebius.config import NebiusConfig
from dstack._internal.core.models.backends.base import BackendType


class NebiusBackend(Backend):
    TYPE: BackendType = BackendType.NEBIUS

    def __init__(self, config: NebiusConfig):
        self.config = config
        self._compute = NebiusCompute(self.config)

    def compute(self) -> NebiusCompute:
        return self._compute
