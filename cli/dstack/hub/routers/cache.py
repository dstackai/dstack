import json
import tempfile
from pathlib import Path

import yaml
from fastapi import HTTPException, status

from dstack.api.backend import dict_backends
from dstack.api.config import dict_config
from dstack.backend.base import CloudBackend
from dstack.hub.db.models import Hub

cache = {}


def get_backend(hub: Hub) -> CloudBackend:
    global cache
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
        backend.__init__(config)
        cache[hub.name] = backend
    return cache.get(hub.name)
