from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional

import yaml


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
    def configure_hub(self, data: Dict):
        pass

    @abstractmethod
    def get_config(self, data: Dict) -> BackendConfig:
        pass

    @abstractmethod
    def parse_args(self, args: list = []):
        pass
