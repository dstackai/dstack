from typing import Optional

from dstack._internal.core.models.backends import BackendType
from dstack._internal.server.services.backends.base import Configurator


def get_configurator(backend_type: BackendType) -> Optional[Configurator]:
    pass
