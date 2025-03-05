from dstack._internal.core.backends.azure.models import AnyAzureCreds, AzureStoredConfig
from dstack._internal.core.backends.base.config import BackendConfig


class AzureConfig(AzureStoredConfig, BackendConfig):
    creds: AnyAzureCreds

    @property
    def allocate_public_ips(self) -> bool:
        if self.public_ips is not None:
            return self.public_ips
        return True
