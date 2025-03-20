from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.vastai.compute import VastAICompute
from dstack._internal.core.backends.vastai.models import VastAIConfig
from dstack._internal.core.models.backends.base import BackendType


class VastAIBackend(Backend):
    TYPE = BackendType.VASTAI
    COMPUTE_CLASS = VastAICompute

    def __init__(self, config: VastAIConfig):
        self.config = config
        self._compute = VastAICompute(self.config)

    def compute(self) -> VastAICompute:
        return self._compute
