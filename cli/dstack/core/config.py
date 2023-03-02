from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict

import yaml


def get_config_path():
    return Path.joinpath(get_dstack_dir(), "config.yaml")


def get_dstack_dir():
    return Path.joinpath(Path.home(), ".dstack")


class Configurator(ABC):
    NAME = ""

    @property
    def name(self):
        return self.NAME or ""

    @abstractmethod
    def configure_cli(self):
        pass

    @abstractmethod
    def configure_hub(self, config: Dict):
        pass

    @abstractmethod
    def get_backend_client(self, config: Dict):
        pass

    @abstractmethod
    def get_config(self, config: Dict):
        pass

    @abstractmethod
    def parse_args(self, args: list = []):
        pass


class BackendConfig(ABC):
    @abstractmethod
    def save(self, path: Path = get_config_path()):
        pass

    @abstractmethod
    def load(self, path: Path = get_config_path()):
        pass

    def load_json(self, json_data):
        for key, value in json_data.items():
            if hasattr(self, key):
                setattr(self, key, value)
