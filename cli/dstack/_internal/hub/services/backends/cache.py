from typing import List, Tuple

from dstack._internal.backend.base import Backend
from dstack._internal.core.error import BackendAuthError
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.services.backends import get_configurator
from dstack._internal.hub.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

cache = {}


async def get_project_backends(project: Project) -> List[Tuple[DBBackend, Backend]]:
    key = project.name
    backends = cache.get(key)
    if backends is not None:
        return backends

    backends = []
    for db_backend in project.backends:
        configurator = get_configurator(db_backend.type)
        if configurator is None:
            continue
        try:
            backend = await run_async(configurator.get_backend, db_backend)
        except BackendAuthError:
            logger.warning(
                "Credentials for %s backend are invalid. Backend will be ignored.", db_backend.name
            )
            continue
        if backends is None:
            logger.warning(
                "Missing dependencies for %s backend. Backend will be ignored.", db_backend.name
            )
            continue
        backends.append((db_backend, backend))

    cache[key] = backends
    return cache[key]


def clear_backend_cache(project_name: str):
    if project_name in cache:
        del cache[project_name]
