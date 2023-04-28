from abc import ABC, abstractmethod
from typing import Dict, List

from dstack.backend.base.config import BackendConfig
from dstack.hub.models import ProjectValues


class BackendConfigError(Exception):
    def __init__(self, message: str = "", code: str = "invalid_config", fields: List[str] = None):
        self.message = message
        self.code = code
        self.fields = fields if fields is not None else []


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
