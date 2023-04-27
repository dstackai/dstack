from typing import Dict

from dstack.backend.base.config import BackendConfig
from dstack.backend.local.config import LocalConfig
from dstack.hub.models import ProjectValues
from dstack.hub.services.backends.base import Configurator


class LocalConfigurator(Configurator):
    @property
    def name(self):
        return "local"

    def configure_hub(self, config_data: Dict) -> ProjectValues:
        return None

    def get_config_from_hub_config_data(
        self, project_name: str, config_data: Dict, auth_data: Dict
    ) -> BackendConfig:
        return LocalConfig(namespace=project_name)
