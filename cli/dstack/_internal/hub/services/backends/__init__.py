import subprocess
from typing import List, Optional

from dstack._internal.hub.models import BackendType
from dstack._internal.hub.services.backends.base import Configurator
from dstack._internal.hub.services.backends.local.configurator import LocalConfigurator

configurators_classes = []

try:
    from dstack._internal.hub.services.backends.aws.configurator import AWSConfigurator

    configurators_classes.append(AWSConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.hub.services.backends.azure.configurator import AzureConfigurator

    configurators_classes.append(AzureConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.hub.services.backends.gcp.configurator import GCPConfigurator

    configurators_classes.append(GCPConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.hub.services.backends.lambdalabs.configurator import LambdaConfigurator

    configurators_classes.append(LambdaConfigurator)
except ImportError:
    pass


def local_backend_available() -> bool:
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


if local_backend_available():
    configurators_classes.append(LocalConfigurator)


backend_type_to_configurator_class_map = {c.NAME: c for c in configurators_classes}


def get_configurator(backend_type: str) -> Optional[Configurator]:
    configurator_class = backend_type_to_configurator_class_map.get(backend_type)
    if configurator_class is None:
        return None
    return configurator_class()


def list_avaialble_backend_types() -> List[BackendType]:
    available_backend_types = []
    for configurator_class in configurators_classes:
        available_backend_types.append(configurator_class.NAME)
    return available_backend_types
