import subprocess
from typing import List, Optional

from dstack.hub.models import BackendType
from dstack.hub.services.backends.aws import AWSConfigurator
from dstack.hub.services.backends.base import Configurator
from dstack.hub.services.backends.gcp import GCPConfigurator
from dstack.hub.services.backends.local import LocalConfigurator

configurators_classes = [
    AWSConfigurator,
    GCPConfigurator,
    LocalConfigurator,
]

try:
    from dstack.hub.services.backends.azure.configurator import AzureConfigurator

    configurators_classes.append(AzureConfigurator)
except ImportError:
    pass


backend_type_to_configurator_class_map = {c.NAME: c for c in configurators_classes}


def get_configurator(backend_type: str) -> Optional[Configurator]:
    return backend_type_to_configurator_class_map[backend_type]()


def list_avaialble_backend_types() -> List[BackendType]:
    available_backend_types = []
    for configurator_class in configurators_classes:
        if configurator_class.NAME == "local":
            if local_backend_available():
                available_backend_types.append(configurator_class.NAME)
        else:
            available_backend_types.append(configurator_class.NAME)
    return available_backend_types


docker_available = None


def local_backend_available() -> bool:
    global docker_available
    if docker_available is None:
        # docker version will exit with 1 if daemon is not running
        try:
            docker_proc = subprocess.run(
                ["docker", "version"],
                stdout=subprocess.DEVNULL,
            )
            docker_available = docker_proc.returncode == 0
        except FileNotFoundError:
            docker_available = False
    return docker_available
