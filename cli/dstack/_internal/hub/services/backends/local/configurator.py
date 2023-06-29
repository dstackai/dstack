from typing import Dict, Tuple

from dstack._internal.backend.local import LocalBackend
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.models import LocalProjectConfig, ProjectValues
from dstack._internal.hub.services.backends.base import Configurator


class LocalConfigurator(Configurator):
    NAME = "local"

    def configure_project(self, project_config: LocalProjectConfig) -> ProjectValues:
        return None

    def create_project(self, project_config: LocalProjectConfig) -> Tuple[Dict, Dict]:
        return {}, {}

    def get_project_config(self, project: Project, include_creds: bool) -> LocalProjectConfig:
        config = LocalConfig(namespace=project.name)
        return LocalProjectConfig(path=str(config.backend_dir))

    def get_backend(self, project: Project) -> LocalBackend:
        config = LocalConfig(namespace=project.name)
        return LocalBackend(config)
