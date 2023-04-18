import json
from typing import Optional

from dstack.api.backend import dict_backends
from dstack.backend.base import CloudBackend
from dstack.core.repo import Repo
from dstack.hub.db.models import Project

cache = {}


def get_backend(project: Project, repo: Optional[Repo]) -> CloudBackend:
    key = project.name if repo is None else (project.name, repo.repo_id, repo.repo_user_id)
    if cache.get(key) is not None:
        return cache[key]
    backend = dict_backends(repo, all_backend=True).get(project.backend)
    configurator = backend.get_configurator()
    json_data = json.loads(str(project.config))
    auth_data = json.loads(str(project.auth))
    config = configurator.get_config_from_hub_config_data(json_data, auth_data)
    backend.__init__(repo=repo, backend_config=config)
    cache[key] = backend
    return cache[key]


def clear_backend_cache(project_name: str):
    if project_name in cache:
        del cache[project_name]
