from typing import List, Optional

from dstack.hub.services.backends.aws import AWSConfigurator
from dstack.hub.services.backends.base import Configurator
from dstack.hub.services.backends.gcp import GCPConfigurator
from dstack.hub.services.backends.local import LocalConfigurator

configurators = [
    AWSConfigurator(),
    GCPConfigurator(),
    LocalConfigurator(),
]


backend_type_to_configurator_map = {c.name: c for c in configurators}


def get_configurator(backend_type: str) -> Optional[Configurator]:
    return backend_type_to_configurator_map[backend_type]
