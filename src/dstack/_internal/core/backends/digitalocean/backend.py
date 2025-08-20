from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.digitalocean.compute import DigitalOceanCompute
from dstack._internal.core.backends.digitalocean.models import DigitalOceanConfig
from dstack._internal.core.models.backends.base import BackendType


class DigitalOceanBackend(Backend):
    TYPE = BackendType.DIGITALOCEAN
    COMPUTE_CLASS = DigitalOceanCompute

    def __init__(self, config: DigitalOceanConfig):
        self.config = config
        self._compute = DigitalOceanCompute(self.config)

    def compute(self) -> DigitalOceanCompute:
        return self._compute
