import json
from typing import Optional

from dstack._internal.backend.base import Backend
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.services.backends import get_configurator
from dstack._internal.hub.utils.common import run_async

cache = {}


async def get_backend(project: Project) -> Optional[Backend]:
    configurator = get_configurator(project.backend)
    if configurator is None:
        return None
    key = project.name
    if cache.get(key) is not None:
        return cache[key]
    json_data = json.loads(str(project.config))
    auth_data = json.loads(str(project.auth))
    config = configurator.get_backend_config_from_hub_config_data(
        project.name, json_data, auth_data
    )
    backend_cls = configurator.get_backend_class()
    backend = await run_async(backend_cls, config)
    cache[key] = backend
    return cache[key]


def clear_backend_cache(project_name: str):
    if project_name in cache:
        del cache[project_name]
