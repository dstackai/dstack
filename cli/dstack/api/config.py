from typing import Dict, List

from dstack import version
from dstack.backend.aws.config import AWSConfig
from dstack.backend.gcp.config import GCPConfigurator
from dstack.backend.hub.config import HUBConfig
from dstack.core.config import BackendConfig

configs_classes = [AWSConfig, GCPConfigurator]
if not version.__is_release__:
    configs_classes.append(HUBConfig)


def list_config() -> List[BackendConfig]:
    configs = [cls() for cls in configs_classes]
    return configs


def dict_config() -> Dict[str, BackendConfig]:
    configs = [cls() for cls in configs_classes]
    names = {}
    for config in configs:
        names[config.name] = config

    return names
