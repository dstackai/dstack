from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from dstack.hub.models import ProjectValues


def get_config_path():
    return Path.joinpath(get_dstack_dir(), "config.yaml")


def get_dstack_dir():
    return Path.joinpath(Path.home(), ".dstack")


class BackendConfig(ABC):
    credentials: Optional[Dict] = None

    @abstractmethod
    def save(self, path: Path = get_config_path()):
        pass

    @abstractmethod
    def load(self, path: Path = get_config_path()):
        pass


class Configurator(ABC):
    NAME = ""

    @property
    def name(self):
        return self.NAME or ""

    @abstractmethod
    def configure_cli(self):
        pass

    @abstractmethod
    def configure_hub(self, config_data: Dict) -> ProjectValues:
        pass

    @abstractmethod
    def get_config_from_hub_config_data(self, config_data: Dict, auth_data: Dict) -> BackendConfig:
        pass

    @abstractmethod
    def register_parser(self, parser):
        pass
