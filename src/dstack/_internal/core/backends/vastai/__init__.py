from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.vastai.compute import VastAICompute
from dstack._internal.core.backends.vastai.config import VastAIConfig
from dstack._internal.core.models.backends.base import BackendType


class VastAIBackend(Backend):
    TYPE: BackendType = BackendType.VASTAI

    def __init__(self, config: VastAIConfig):
        self.config = config
        self._compute = VastAICompute(self.config)

    def compute(self) -> VastAICompute:
        return self._compute
