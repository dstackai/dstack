from dstack._internal.core.backends.azure import auth
from dstack._internal.core.backends.azure.compute import AzureCompute
from dstack._internal.core.backends.azure.models import AzureConfig
from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.models.backends.base import BackendType


class AzureBackend(Backend):
    TYPE = BackendType.AZURE
    COMPUTE_CLASS = AzureCompute

    def __init__(self, config: AzureConfig):
        self.config = config
        self.credential, _ = auth.authenticate(self.config.creds)
        self._compute = AzureCompute(
            config=self.config,
            credential=self.credential,
        )

    def compute(self) -> AzureCompute:
        return self._compute
