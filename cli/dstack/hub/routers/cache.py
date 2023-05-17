import json

from dstack.backend.base import Backend
from dstack.hub.db.models import Project
from dstack.hub.services.backends import get_configurator

cache = {}


def get_backend(project: Project) -> Backend:
    key = project.name
    if cache.get(key) is not None:
        return cache[key]
    configurator = get_configurator(project.backend)
    json_data = json.loads(str(project.config))
    auth_data = json.loads(str(project.auth))
    config = configurator.get_backend_config_from_hub_config_data(
        project.name, json_data, auth_data
    )
    backend_cls = configurator.get_backend_class()
    backend = backend_cls(backend_config=config)
    cache[key] = backend
    return cache[key]


def clear_backend_cache(project_name: str):
    if project_name in cache:
        del cache[project_name]
