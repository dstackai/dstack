from typing import Dict, List, Optional

from dstack.backend.aws import AwsBackend
from dstack.backend.base import Backend, BackendType, RemoteBackend
from dstack.backend.gcp import GCPBackend
from dstack.backend.hub import HubBackend
from dstack.backend.local import LocalBackend
from dstack.core.repo import Repo

backends_classes = [HubBackend, AwsBackend, GCPBackend, LocalBackend]


def get_all_backends(repo: Optional[Repo]):
    return [backend_cls(repo=repo) for backend_cls in backends_classes]


def list_backends(repo: Optional[Repo], all_backend: bool = False) -> List[Backend]:
    return [backend for backend in get_all_backends(repo) if all_backend or backend.loaded]


def list_remote_backends(repo: Optional[Repo]) -> List[RemoteBackend]:
    return [b for b in list_backends(repo) if b.type is BackendType.REMOTE]


def dict_backends(repo: Optional[Repo], all_backend: bool = False) -> Dict[str, Backend]:
    return {backend.name: backend for backend in list_backends(repo, all_backend=all_backend)}


def get_backend_by_name(repo: Repo, name: str) -> Optional[Backend]:
    return dict_backends(repo=repo).get(name)


def get_current_remote_backend(repo: Optional[Repo] = None) -> Optional[RemoteBackend]:
    remote_backends = list_remote_backends(repo=repo)
    if len(remote_backends) == 0:
        return None
    return remote_backends[0]


def get_local_backend(repo: Repo) -> LocalBackend:
    return LocalBackend(repo=repo)
