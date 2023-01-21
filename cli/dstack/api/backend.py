from typing import List, Dict, Optional
from dstack.backend import Backend
from dstack.core.error import BackendError
from dstack.backend.aws import AwsBackend
from dstack.backend.local import LocalBackend

DEFAULT_REMOTE = "aws"
DEFAULT = "local"


def list_backends() -> List[Backend]:
    all_backends = [cls() for cls in Backend.__subclasses__()]  # pylint: disable=E1101
    return [current_backend for current_backend in all_backends if current_backend.loaded()]


def dict_backends() -> Dict[str, Backend]:
    all_backends = [cls() for cls in Backend.__subclasses__()]  # pylint: disable=E1101
    d = {}
    for current_backend in all_backends:
        if current_backend.loaded():
            d[current_backend.name] = current_backend
    return d


def get_backend_by_name(name: str) -> Optional[Backend]:
    all_backends = [cls() for cls in Backend.__subclasses__()]  # pylint: disable=E1101
    for current_backend in all_backends:
        if current_backend.loaded():
            if current_backend.NAME == name:
                return current_backend
    raise BackendError(f"Not a backend named {name}")