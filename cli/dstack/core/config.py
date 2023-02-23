from abc import ABC, abstractmethod
from pathlib import Path

import yaml


def get_config_path():
    return Path.joinpath(get_dstack_dir(), "config.yaml")


def get_dstack_dir():
    return Path.joinpath(Path.home(), ".dstack")


class BackendConfig(ABC):
    NAME = ""

    _configured = False

    @property
    def name(self):
        return self.NAME or ""

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

    @abstractmethod
    def configure(self):
        pass

    @property
    def configured(self):
        return self._configured
