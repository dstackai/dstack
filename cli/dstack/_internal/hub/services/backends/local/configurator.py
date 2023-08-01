import json
from typing import Dict, Tuple

from dstack._internal.backend.local import LocalBackend
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.schemas import BackendValues, LocalBackendConfig
from dstack._internal.hub.services.backends.base import Configurator


class LocalConfigurator(Configurator):
    NAME = "local"

    def configure_backend(self, backend_config: LocalBackendConfig) -> BackendValues:
        return None

    def create_backend(
        self, project_name: str, backend_config: LocalBackendConfig
    ) -> Tuple[Dict, Dict]:
        return {"namespace": project_name}, {}

    def get_backend_config(self, db_backend: DBBackend, include_creds: bool) -> LocalBackendConfig:
        config = json.loads(db_backend.config)
        backend_config = LocalConfig(namespace=config.get("namespace", "main"))
        return LocalBackendConfig(path=str(backend_config.backend_dir))

    def get_backend(self, db_backend: DBBackend) -> LocalBackend:
        config = json.loads(db_backend.config)
        backend_config = LocalConfig(namespace=config.get("namespace", "main"))
        return LocalBackend(backend_config)
