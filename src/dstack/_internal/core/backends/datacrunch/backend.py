from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.datacrunch.compute import DataCrunchCompute
from dstack._internal.core.backends.datacrunch.models import DataCrunchConfig
from dstack._internal.core.models.backends.base import BackendType


class DataCrunchBackend(Backend):
    TYPE = BackendType.DATACRUNCH
    COMPUTE_CLASS = DataCrunchCompute

    def __init__(self, config: DataCrunchConfig):
        self.config = config
        self._compute = DataCrunchCompute(self.config)

    def compute(self) -> DataCrunchCompute:
        return self._compute
