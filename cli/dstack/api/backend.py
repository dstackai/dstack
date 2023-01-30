from typing import List, Dict, Optional
from dstack.backend import Backend
from dstack.core.error import BackendError
from dstack.backend.aws import AwsBackend
from dstack.backend.gcp import GCPBackend
from dstack.backend.local import LocalBackend


DEFAULT_REMOTE = "aws"
DEFAULT = "local"


backends_classes = [AwsBackend, GCPBackend, LocalBackend]


def get_all_backends():
    return [backend_cls() for backend_cls in backends_classes]


def list_backends() -> List[Backend]:
    return [backend for backend in get_all_backends() if backend.loaded()]


def dict_backends() -> Dict[str, Backend]:
    return {backend.name: backend for backend in list_backends()}


def get_backend_by_name(name: str) -> Optional[Backend]:
    backend = dict_backends().get(name)
    if backend is None:
        raise BackendError(f"Backend {name} not found")
    return backend
