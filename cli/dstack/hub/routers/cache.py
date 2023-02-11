import json

import yaml
import tempfile
from pathlib import Path
from fastapi import HTTPException, status
from multiprocessing import Manager

from dstack.backend.base import RemoteBackend
from dstack.hub.db.models import Hub
from dstack.api.backend import dict_backends
from dstack.api.config import dict_config

manager = Manager()

cache = manager.dict()


def get_backend(hub: Hub) -> RemoteBackend:
    if cache.get(hub.name) is None:
        if hub.config == "":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Empty config for hub = {hub.name}",
            )
        backend = dict_backends(all_backend=True).get(hub.backend)
        if backend is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Backend not found for {hub.backend}",
            )
        config = dict_config().get(hub.backend)
        if backend is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Config not found for {hub.backend}",
            )
        json_data = json.loads(hub.config)
        config.load_json(json_data)
        backend.backend_config = config
        cache[hub.name] = backend
    return cache.get(hub.name)
