from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.local.compute import LocalCompute
from dstack._internal.core.models.backends.base import BackendType


class LocalBackend(Backend):
    TYPE: BackendType = BackendType.LOCAL

    def __init__(self):
        self._compute = LocalCompute()

    def compute(self) -> LocalCompute:
        return self._compute
