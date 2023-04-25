from abc import ABC, abstractmethod
from pathlib import Path


def get_config_path():
    return Path.joinpath(get_dstack_dir(), "config.yaml")


def get_dstack_dir():
    return Path.joinpath(Path.home(), ".dstack")


class BackendConfig(ABC):
    pass
