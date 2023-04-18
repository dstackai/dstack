import os.path

from dstack.backend.base.storage import Storage
from dstack.core.repo import RepoRef


def delete_workflow_cache(storage: Storage, repo_ref: RepoRef, workflow: str):
    storage.delete_prefix(
        keys_prefix=os.path.join(_get_cache_dir(repo_ref.repo_id, repo_ref.repo_user_id), workflow)
        + "/"
    )


def _get_cache_dir(repo_id: str, username: str) -> str:
    return os.path.join("cache", repo_id, username)
