import subprocess
from typing import List, Optional

from dstack.hub.models import BackendType
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


docker_available = None


def list_avaialble_backend_types() -> List[BackendType]:
    global docker_available
    configurators = [AWSConfigurator(), GCPConfigurator()]
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
    if docker_available:
        configurators.append(LocalConfigurator())
    return [c.name for c in configurators]
