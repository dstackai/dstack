from abc import ABC, abstractmethod
from typing import List, Optional

from dstack.backend.base.storage import Storage
from dstack.core.repo import RepoAddress
from dstack.core.secret import Secret


class SecretsManager(ABC):
    @abstractmethod
    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        pass

    @abstractmethod
    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    @abstractmethod
    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    @abstractmethod
    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        pass


def list_secret_names(storage: Storage, repo_address: RepoAddress) -> List[str]:
    secret_head_prefix = _get_secret_heads_keys_prefix(repo_address)
    secret_heads_keys = storage.list_objects(secret_head_prefix)
    secret_names = []
    for secret_head_key in secret_heads_keys:
        secret_name = secret_head_key[len(secret_head_prefix) :]
        secret_names.append(secret_name)
    return secret_names


def get_secret(
    secrets_manager: SecretsManager,
    repo_address: RepoAddress,
    secret_name: str,
) -> Optional[Secret]:
    return secrets_manager.get_secret(repo_address, secret_name)


def add_secret(
    storage: Storage,
    secrets_manager: SecretsManager,
    repo_address: RepoAddress,
    secret: Secret,
):
    secrets_manager.add_secret(repo_address, secret)
    storage.put_object(
        key=_get_secret_head_key(repo_address, secret.secret_name),
        content="",
    )


def update_secret(
    storage: Storage,
    secrets_manager: SecretsManager,
    repo_address: RepoAddress,
    secret: Secret,
):
    secrets_manager.update_secret(repo_address, secret)
    storage.put_object(
        key=_get_secret_head_key(repo_address, secret.secret_name),
        content="",
    )


def delete_secret(
    storage: Storage,
    secrets_manager: SecretsManager,
    repo_address: RepoAddress,
    secret_name: str,
):
    secrets_manager.delete_secret(repo_address, secret_name)
    storage.delete_object(_get_secret_head_key(repo_address, secret_name))


def _get_secret_heads_dir(repo_address: RepoAddress) -> str:
    return f"secrets/{repo_address.path()}/"


def _get_secret_heads_keys_prefix(repo_address: RepoAddress) -> str:
    prefix = _get_secret_heads_dir(repo_address)
    key = f"{prefix}l;"
    return key


def _get_secret_head_key(repo_address: RepoAddress, secret_name: str) -> str:
    prefix = _get_secret_heads_dir(repo_address)
    key = f"{prefix}l;{secret_name}"
    return key
