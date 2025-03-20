from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.runpod.compute import RunpodCompute
from dstack._internal.core.backends.runpod.models import RunpodConfig
from dstack._internal.core.models.backends.base import BackendType


class RunpodBackend(Backend):
    TYPE = BackendType.RUNPOD
    COMPUTE_CLASS = RunpodCompute

    def __init__(self, config: RunpodConfig):
        self.config = config
        self._compute = RunpodCompute(self.config)

    def compute(self) -> RunpodCompute:
        return self._compute
