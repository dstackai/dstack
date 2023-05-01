import os.path

from dstack.backend.base.storage import Storage


def delete_workflow_cache(storage: Storage, repo_id: str, repo_user_id: str, workflow: str):
    storage.delete_prefix(
        keys_prefix=os.path.join(_get_cache_dir(repo_id, repo_user_id), workflow) + "/"
    )


def _get_cache_dir(repo_id: str, username: str) -> str:
    return os.path.join("cache", repo_id, username)
