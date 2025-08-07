from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.hotaisle.compute import HotAisleCompute
from dstack._internal.core.backends.hotaisle.models import HotAisleConfig
from dstack._internal.core.models.backends.base import BackendType


class HotAisleBackend(Backend):
    TYPE = BackendType.HOTAISLE
    COMPUTE_CLASS = HotAisleCompute

    def __init__(self, config: HotAisleConfig):
        self.config = config
        self._compute = HotAisleCompute(self.config)

    def compute(self) -> HotAisleCompute:
        return self._compute
