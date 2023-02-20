from typing import Dict, List, Optional

from dstack import version
from dstack.backend.aws import AwsBackend
from dstack.backend.base import Backend, RemoteBackend
from dstack.backend.hub import HubBackend
from dstack.backend.local import LocalBackend

DEFAULT_REMOTE = "aws"
DEFAULT = "local"

backends_classes = [AwsBackend, LocalBackend]
if not version.__is_release__:
    backends_classes.append(HubBackend)


def get_all_backends():
    return [backend_cls() for backend_cls in backends_classes]


def list_backends(all_backend: bool = False) -> List[Backend]:
    l = []
    for backend in get_all_backends():
        if all_backend:
            l.append(backend)
        elif backend.loaded:
            l.append(backend)
    return l


def dict_backends(all_backend: bool = False) -> Dict[str, Backend]:
    return {backend.name: backend for backend in list_backends(all_backend=all_backend)}


def get_backend_by_name(name: str) -> Optional[Backend]:
    return dict_backends().get(name)


def get_current_remote_backend() -> Optional[RemoteBackend]:
    return get_backend_by_name(DEFAULT_REMOTE)


def get_local_backend() -> LocalBackend:
    return LocalBackend()
