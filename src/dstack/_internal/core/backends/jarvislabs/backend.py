from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.jarvislabs.compute import JarvisLabsCompute
from dstack._internal.core.backends.jarvislabs.models import JarvisLabsConfig
from dstack._internal.core.models.backends.base import BackendType


class JarvisLabsBackend(Backend):
    TYPE = BackendType.JARVISLABS
    COMPUTE_CLASS = JarvisLabsCompute

    def __init__(self, config: JarvisLabsConfig):
        self.config = config
        self._compute = JarvisLabsCompute(self.config)

    def compute(self) -> JarvisLabsCompute:
        return self._compute
