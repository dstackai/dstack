from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.daytona.compute import DaytonaCompute
from dstack._internal.core.backends.daytona.models import DaytonaConfig
from dstack._internal.core.models.backends.base import BackendType


class DaytonaBackend(Backend):
    TYPE = BackendType.DAYTONA
    COMPUTE_CLASS = DaytonaCompute

    def __init__(self, config: DaytonaConfig):
        self.config = config
        self._compute = DaytonaCompute(self.config)

    def compute(self) -> DaytonaCompute:
        return self._compute
