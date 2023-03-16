import json

from fastapi import HTTPException, status

from dstack.api.backend import dict_backends
from dstack.backend.base import CloudBackend
from dstack.hub.db.models import Project

cache = {}


def get_backend(project: Project) -> CloudBackend:
    global cache
    if cache.get(project.name) is None:
        if project.config == "":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Empty config for project = {project.name}",
            )
        backend = dict_backends(all_backend=True).get(project.backend)
        if backend is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Backend not found for {project.backend}",
            )
        configurator = backend.get_configurator()
        if configurator is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Configurator not found for {project.backend}",
            )
        json_data = json.loads(str(project.config))
        config = configurator.get_config(json_data)
        if project.auth is not None:
            config.credentials = json.loads(str(project.auth))
        backend.__init__(backend_config=config)
        cache[project.name] = backend
    return cache.get(project.name)
