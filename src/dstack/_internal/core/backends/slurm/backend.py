from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.slurm.compute import SlurmCompute
from dstack._internal.core.backends.slurm.models import SlurmConfig
from dstack._internal.core.models.backends.base import BackendType


class SlurmBackend(Backend):
    TYPE = BackendType.SLURM
    COMPUTE_CLASS = SlurmCompute

    def __init__(self, config: SlurmConfig):
        self.config = config
        self._compute = SlurmCompute(self.config)

    def compute(self) -> SlurmCompute:
        return self._compute
