from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.cloudrift.compute import CloudRiftCompute
from dstack._internal.core.backends.cloudrift.models import CloudRiftConfig
from dstack._internal.core.models.backends.base import BackendType


class CloudRiftBackend(Backend):
    TYPE = BackendType.CLOUDRIFT
    COMPUTE_CLASS = CloudRiftCompute

    def __init__(self, config: CloudRiftConfig):
        self.config = config
        self._compute = CloudRiftCompute(self.config)

    def compute(self) -> CloudRiftCompute:
        return self._compute
