from typing import Dict, List

from dstack.api.backend import backends_classes
from dstack.core.config import Configurator


def list_config() -> List[Configurator]:
    configs = [cls.get_configurator() for cls in backends_classes]
    return [config for config in configs if config is not None]


def dict_configurator() -> Dict[str, Configurator]:
    configs = list_config()
    return {config.name: config for config in configs}
