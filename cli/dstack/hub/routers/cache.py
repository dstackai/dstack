import json
from typing import Optional

from dstack.api.internal.backend import get_backend_class
from dstack.backend.base import Backend
from dstack.core.repo import Repo
from dstack.hub.db.models import Project
from dstack.hub.services.backends import get_configurator

cache = {}


def get_backend(project: Project) -> Backend:
    key = project.name
    if cache.get(key) is not None:
        return cache[key]
    backend_cls = get_backend_class(project.backend)
    configurator = get_configurator(project.backend)
    json_data = json.loads(str(project.config))
    auth_data = json.loads(str(project.auth))
    config = configurator.get_config_from_hub_config_data(project.name, json_data, auth_data)
    backend = backend_cls(backend_config=config)
    cache[key] = backend
    return cache[key]


def clear_backend_cache(project_name: str):
    if project_name in cache:
        del cache[project_name]
