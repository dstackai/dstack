from typing import Optional

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.nebius.compute import NebiusCompute
from dstack._internal.core.backends.nebius.models import NebiusConfig
from dstack._internal.core.models.backends.base import BackendType


class NebiusBackend(Backend):
    TYPE = BackendType.NEBIUS
    COMPUTE_CLASS = NebiusCompute

    def __init__(self, config: NebiusConfig, compute: Optional[NebiusCompute] = None):
        self.config = config
        self._compute = compute if compute is not None else NebiusCompute(self.config)

    def compute(self) -> NebiusCompute:
        return self._compute
