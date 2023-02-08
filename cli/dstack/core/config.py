from abc import ABC
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

    def save(self, path: Path = get_config_path()):
        pass

    def load(self, path: Path = get_config_path()):
        ...

    def configure(self):
        ...

    @property
    def configured(self):
        return self._configured
