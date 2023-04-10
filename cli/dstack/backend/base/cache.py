import os.path

from dstack.backend.base.storage import Storage
from dstack.core.repo import RepoAddress


def delete_workflow_cache(storage: Storage, repo_name, username: str, workflow: str):
    storage.delete_prefix(
        keys_prefix=os.path.join(_get_cache_dir(repo_name, username), workflow) + "/"
    )


def _get_cache_dir(repo_name: str, username: str) -> str:
    return os.path.join("cache", repo_name, username)
