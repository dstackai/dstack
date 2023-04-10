import json

from dstack.api.backend import dict_backends
from dstack.backend.base import CloudBackend
from dstack.hub.db.models import Project

cache = {}


def get_backend(project: Project) -> CloudBackend:
    if cache.get(project.name) is not None:
        return cache[project.name]
    backend = dict_backends(all_backend=True).get(project.backend)
    configurator = backend.get_configurator()
    json_data = json.loads(str(project.config))
    auth_data = json.loads(str(project.auth))
    config = configurator.get_config_from_hub_config_data(json_data, auth_data)
    backend.__init__(backend_config=config)
    cache[project.name] = backend
    return cache[project.name]


def clear_backend_cache(project_name: str):
    if project_name in cache:
        del cache[project_name]
