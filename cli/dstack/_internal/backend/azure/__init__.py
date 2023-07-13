from typing import Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential, DefaultAzureCredential

from dstack._internal.backend.azure.compute import AzureCompute
from dstack._internal.backend.azure.config import AzureConfig
from dstack._internal.backend.azure.logs import AzureLogging
from dstack._internal.backend.azure.secrets import AzureSecretsManager
from dstack._internal.backend.azure.storage import AzureStorage
from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.core.error import BackendAuthError


class AzureBackend(ComponentBasedBackend):
    NAME = "azure"

    def __init__(self, backend_config: AzureConfig, credential: Optional[TokenCredential] = None):
        self.backend_config = backend_config
        if credential is None:
            if backend_config.credentials["type"] == "client":
                credential = ClientSecretCredential(
                    tenant_id=backend_config.tenant_id,
                    client_id=backend_config.credentials["client_id"],
                    client_secret=backend_config.credentials["client_secret"],
                )
            else:
                credential = DefaultAzureCredential()
        try:
            self._secrets_manager = AzureSecretsManager(
                credential=credential,
                vault_url=self.backend_config.vault_url,
            )
            self._storage = AzureStorage(
                credential=credential,
                storage_account=self.backend_config.storage_account,
            )
            self._compute = AzureCompute(
                credential=credential,
                azure_config=self.backend_config,
            )
            self._logging = AzureLogging(
                credential=credential,
                subscription_id=self.backend_config.subscription_id,
                resource_group=self.backend_config.resource_group,
                storage_account=self.backend_config.storage_account,
            )
        except ClientAuthenticationError:
            raise BackendAuthError()

    @classmethod
    def load(cls) -> Optional["AzureBackend"]:
        config = AzureConfig.load()
        if config is None:
            return None
        return cls(backend_config=config, credential=DefaultAzureCredential())

    def storage(self) -> AzureStorage:
        return self._storage

    def compute(self) -> AzureCompute:
        return self._compute

    def secrets_manager(self) -> AzureSecretsManager:
        return self._secrets_manager

    def logging(self) -> AzureLogging:
        return self._logging
