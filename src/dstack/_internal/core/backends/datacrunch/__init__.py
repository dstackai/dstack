from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.datacrunch.compute import DataCrunchCompute
from dstack._internal.core.backends.datacrunch.config import DataCrunchConfig
from dstack._internal.core.models.backends.base import BackendType


class DataCrunchBackend(Backend):
    TYPE: BackendType = BackendType.DATACRUNCH

    def __init__(self, config: DataCrunchConfig):
        self.config = config
        self._compute = DataCrunchCompute(self.config)

    def compute(self) -> DataCrunchCompute:
        return self._compute
