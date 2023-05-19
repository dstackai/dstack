import subprocess
from typing import Dict, Tuple

from dstack.backend.local import LocalBackend
from dstack.backend.local.config import LocalConfig
from dstack.hub.models import LocalProjectConfig, Project, ProjectValues
from dstack.hub.services.backends.base import Configurator


class LocalConfigurator(Configurator):
    NAME = "local"

    def get_backend_class(self) -> type:
        return LocalBackend

    def configure_project(self, config_data: Dict) -> ProjectValues:
        return None

    def get_backend_config_from_hub_config_data(
        self, project_name: str, config_data: Dict, auth_data: Dict
    ) -> LocalConfig:
        return LocalConfig(namespace=project_name)

    def create_config_auth_data_from_project_config(
        self, project_config: LocalProjectConfig
    ) -> Tuple[Dict, Dict]:
        return {}, {}

    def get_project_config_from_project(
        self, project: Project, include_creds: bool
    ) -> LocalProjectConfig:
        config = self.get_backend_config_from_hub_config_data(
            project.name, project.config, project.auth
        )
        return LocalProjectConfig(path=str(config.backend_dir))
