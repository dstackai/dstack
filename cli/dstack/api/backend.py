from typing import Dict, List, Optional

from dstack.backend.aws import AwsBackend
from dstack.backend.base import Backend, RemoteBackend
from dstack.backend.gcp import GCPBackend
from dstack.backend.local import LocalBackend
from dstack.core.error import BackendError

DEFAULT_REMOTE = "aws"
DEFAULT = "local"


# backends_classes = [AwsBackend, GCPBackend, LocalBackend]
# for testing
backends_classes = [GCPBackend, LocalBackend]


def get_all_backends():
    return [backend_cls() for backend_cls in backends_classes]


def list_backends() -> List[Backend]:
    return [backend for backend in get_all_backends() if backend.loaded]


def dict_backends() -> Dict[str, Backend]:
    return {backend.name: backend for backend in list_backends()}


def get_backend_by_name(name: str) -> Optional[Backend]:
    backend = dict_backends().get(name)
    if backend is None:
        raise BackendError(f"Backend {name} not found")
    return backend


def get_current_remote_backend() -> RemoteBackend:
    return get_backend_by_name(DEFAULT_REMOTE)


def get_local_backend() -> LocalBackend:
    return LocalBackend()
