from dstack._internal.core.backends.verda.compute import VerdaCompute
from dstack._internal.core.backends.verda.models import VerdaConfig
from dstack._internal.core.models.backends.base import BackendType


class DataCrunchCompute(VerdaCompute):
    def __init__(self, config: VerdaConfig, backend_type: BackendType):
        super().__init__(config, backend_type)
