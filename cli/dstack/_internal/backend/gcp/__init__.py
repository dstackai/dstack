import warnings
from typing import Optional

import google.auth
from google.auth._default import _CLOUD_SDK_CREDENTIALS_WARNING
from google.auth.credentials import Credentials

from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.backend.gcp.auth import authenticate
from dstack._internal.backend.gcp.compute import GCPCompute
from dstack._internal.backend.gcp.config import GCPConfig
from dstack._internal.backend.gcp.logs import GCPLogging
from dstack._internal.backend.gcp.secrets import GCPSecretsManager
from dstack._internal.backend.gcp.storage import GCPStorage

warnings.filterwarnings("ignore", message=_CLOUD_SDK_CREDENTIALS_WARNING)


class GCPBackend(ComponentBasedBackend):
    NAME = "gcp"

    def __init__(
        self,
        backend_config: GCPConfig,
        credentials: Optional[Credentials] = None,
    ):
        self.backend_config = backend_config
        if credentials is None:
            credentials = authenticate(backend_config)
        self._storage = GCPStorage(
            project_id=self.backend_config.project_id,
            bucket_name=self.backend_config.bucket_name,
            credentials=credentials,
        )
        self._compute = GCPCompute(gcp_config=self.backend_config, credentials=credentials)
        self._secrets_manager = GCPSecretsManager(
            project_id=self.backend_config.project_id,
            bucket_name=self.backend_config.bucket_name,
            credentials=credentials,
        )
        self._logging = GCPLogging(
            project_id=self.backend_config.project_id,
            bucket_name=self.backend_config.bucket_name,
            credentials=credentials,
        )

    def storage(self) -> GCPStorage:
        return self._storage

    def compute(self) -> GCPCompute:
        return self._compute

    def secrets_manager(self) -> GCPSecretsManager:
        return self._secrets_manager

    def logging(self) -> GCPLogging:
        return self._logging

    @classmethod
    def load(cls) -> Optional["GCPBackend"]:
        config = GCPConfig.load()
        if config is None:
            return None
        credentials, _ = google.auth.default()
        return cls(
            backend_config=config,
            credentials=credentials,
        )
