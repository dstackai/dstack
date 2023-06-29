import os.path

from dstack._internal.backend.base.storage import Storage
from dstack._internal.utils.escape import escape_head


def delete_configuration_cache(
    storage: Storage, repo_id: str, hub_user_name: str, configuration_path: str
):
    configuration_key = escape_head(configuration_path)
    storage.delete_prefix(
        keys_prefix=os.path.join(_get_cache_dir(repo_id, hub_user_name), configuration_key) + "/"
    )


def _get_cache_dir(repo_id: str, username: str) -> str:
    return os.path.join("cache", repo_id, username)
