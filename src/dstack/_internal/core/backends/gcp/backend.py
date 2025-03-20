from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.gcp.compute import GCPCompute
from dstack._internal.core.backends.gcp.models import GCPConfig
from dstack._internal.core.models.backends.base import BackendType


class GCPBackend(Backend):
    TYPE = BackendType.GCP
    COMPUTE_CLASS = GCPCompute

    def __init__(self, config: GCPConfig):
        self.config = config
        self._compute = GCPCompute(self.config)
        # self._check_credentials()

    def compute(self) -> GCPCompute:
        return self._compute
