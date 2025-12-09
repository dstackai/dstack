from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.verda.compute import VerdaCompute
from dstack._internal.core.backends.verda.models import VerdaConfig
from dstack._internal.core.models.backends.base import BackendType


class VerdaBackend(Backend):
    TYPE = BackendType.VERDA
    COMPUTE_CLASS = VerdaCompute

    def __init__(self, config: VerdaConfig):
        self.config = config
        self._compute = VerdaCompute(self.config, self.TYPE)

    def compute(self) -> VerdaCompute:
        return self._compute
