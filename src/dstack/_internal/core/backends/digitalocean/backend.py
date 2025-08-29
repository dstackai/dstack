from dstack._internal.core.backends.digitalocean.compute import DigitalOceanCompute
from dstack._internal.core.backends.digitalocean_base.backend import BaseDigitalOceanBackend
from dstack._internal.core.backends.digitalocean_base.models import BaseDigitalOceanConfig
from dstack._internal.core.models.backends.base import BackendType


class DigitalOceanBackend(BaseDigitalOceanBackend):
    TYPE = BackendType.DIGITALOCEAN
    COMPUTE_CLASS = DigitalOceanCompute

    def __init__(self, config: BaseDigitalOceanConfig, api_url: str):
        self.config = config
        self._compute = DigitalOceanCompute(self.config, api_url=api_url, type=self.TYPE)

    def compute(self) -> DigitalOceanCompute:
        return self._compute
