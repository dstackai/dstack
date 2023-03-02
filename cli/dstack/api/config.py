from typing import Dict, List

from dstack.api.backend import list_backends
from dstack.core.config import Configurator


def list_config() -> List[Configurator]:
    configs = [
        cls.get_configurator()
        for cls in list_backends(all_backend=True)
        if cls.get_configurator() is not None
    ]
    return configs


def dict_configurator() -> Dict[str, Configurator]:
    configs = [
        cls.get_configurator()
        for cls in list_backends(all_backend=True)
        if cls.get_configurator() is not None
    ]
    names = {}
    for config in configs:
        names[config.name] = config

    return names
