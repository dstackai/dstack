from dstack._internal.core.backends.amddevcloud.compute import AMDDevCloudCompute
from dstack._internal.core.backends.digitalocean_base.backend import BaseDigitalOceanBackend
from dstack._internal.core.backends.digitalocean_base.models import BaseDigitalOceanConfig
from dstack._internal.core.models.backends.base import BackendType


class AMDDevCloudBackend(BaseDigitalOceanBackend):
    TYPE = BackendType.AMDDEVCLOUD
    COMPUTE_CLASS = AMDDevCloudCompute

    def __init__(self, config: BaseDigitalOceanConfig, api_url: str):
        self.config = config
        self._compute = AMDDevCloudCompute(self.config, api_url=api_url, type=self.TYPE)

    def compute(self) -> AMDDevCloudCompute:
        return self._compute
