from abc import ABC, abstractmethod
from typing import Dict

from dstack.core.config import BackendConfig
from dstack.hub.models import ProjectValues


class Configurator(ABC):
    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def configure_hub(self, config_data: Dict) -> ProjectValues:
        pass

    @abstractmethod
    def get_config_from_hub_config_data(
        self, project_name: str, config_data: Dict, auth_data: Dict
    ) -> BackendConfig:
        pass
