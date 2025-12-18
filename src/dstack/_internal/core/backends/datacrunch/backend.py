from dstack._internal.core.backends.datacrunch.compute import DataCrunchCompute
from dstack._internal.core.backends.verda.backend import VerdaBackend
from dstack._internal.core.backends.verda.models import VerdaConfig
from dstack._internal.core.models.backends.base import BackendType


# Deprecated
# TODO: Remove in 0.21
class DataCrunchBackend(VerdaBackend):
    TYPE = BackendType.DATACRUNCH
    COMPUTE_CLASS = DataCrunchCompute

    def __init__(self, config: VerdaConfig):
        self.config = config
        self._compute = DataCrunchCompute(self.config, self.TYPE)

    def compute(self) -> DataCrunchCompute:
        return self._compute
