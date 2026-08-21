from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.seeweb.compute import SeewebCompute
from dstack._internal.core.backends.seeweb.models import SeewebConfig
from dstack._internal.core.models.backends.base import BackendType


class SeewebBackend(Backend):
    TYPE = BackendType.SEEWEB
    COMPUTE_CLASS = SeewebCompute

    def __init__(self, config: SeewebConfig):
        self.config = config
        self._compute = SeewebCompute(self.config)

    def compute(self) -> SeewebCompute:
        return self._compute
