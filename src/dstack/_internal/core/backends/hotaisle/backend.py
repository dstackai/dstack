from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.hotaisle.compute import HotaisleCompute
from dstack._internal.core.backends.hotaisle.models import HotaisleConfig
from dstack._internal.core.models.backends.base import BackendType


class HotaisleBackend(Backend):
    TYPE = BackendType.HOTAISLE
    COMPUTE_CLASS = HotaisleCompute

    def __init__(self, config: HotaisleConfig):
        self.config = config
        self._compute = HotaisleCompute(self.config)

    def compute(self) -> HotaisleCompute:
        return self._compute
