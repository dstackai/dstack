import json
import re
from typing import List, Optional

from dstack._internal.backend.base.secrets import SecretsManager
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.repo import (
    LocalRepoInfo,
    RemoteRepoCredentials,
    RemoteRepoInfo,
    RepoHead,
    RepoProtocol,
    RepoSpec,
)
from dstack._internal.utils.escape import unescape_head

# repo_id, last_run_at, tags_count, repo_type, repo_info
repo_head_re = re.compile(r"([^;]+);(\d+);(\d+);(remote|local);(.*)")


def list_repo_heads(storage: Storage) -> List[RepoHead]:
    repo_heads_prefix = _get_repo_heads_prefix()
    repo_heads_keys = storage.list_objects(repo_heads_prefix)
    repo_heads = []
    for repo_head_key in repo_heads_keys:
        repo_head = _parse_repo_head_filename(repo_head_key)
        if repo_head is not None:
            repo_heads.append(repo_head)
    return repo_heads


def update_repo_last_run_at(storage: Storage, repo_spec: RepoSpec, last_run_at: int):
    repo_head = _get_repo_head(storage, repo_spec.repo_ref.repo_id)
    if repo_head is None:
        repo_info = None
        if repo_spec.repo_data.repo_type == "remote":
            repo_info = RemoteRepoInfo(
                repo_host_name=repo_spec.repo_data.repo_host_name,
                repo_port=repo_spec.repo_data.repo_port,
                repo_user_name=repo_spec.repo_data.repo_user_name,
                repo_name=repo_spec.repo_data.repo_name,
            )
        elif repo_spec.repo_data.repo_type == "local":
            repo_info = LocalRepoInfo(repo_dir=unescape_head(repo_spec.repo_data.repo_dir))
        repo_head = RepoHead(
            repo_id=repo_spec.repo_ref.repo_id,
            repo_info=repo_info,
        )
    repo_head.last_run_at = last_run_at
    _create_or_update_repo_head(storage, repo_head)


def delete_repo(storage: Storage, repo_id: str):
    _delete_repo_head(storage, repo_id)


def get_repo_credentials(
    secrets_manager: SecretsManager, repo_id: str
) -> Optional[RemoteRepoCredentials]:
    credentials_value = secrets_manager.get_credentials(repo_id)
    if credentials_value is None:
        return None
    credentials_data = json.loads(credentials_value)
    return RemoteRepoCredentials(**credentials_data)


def save_repo_credentials(
    secrets_manager: SecretsManager, repo_id, repo_credentials: RemoteRepoCredentials
):
    credentials_data = {"protocol": repo_credentials.protocol.value}
    if repo_credentials.protocol == RepoProtocol.HTTPS and repo_credentials.oauth_token:
        credentials_data["oauth_token"] = repo_credentials.oauth_token
    elif repo_credentials.protocol == RepoProtocol.SSH:
        if repo_credentials.private_key:
            credentials_data["private_key"] = repo_credentials.private_key
        else:
            raise Exception("No private key is specified")

    credentials_value = secrets_manager.get_credentials(repo_id)
    if credentials_value is not None:
        secrets_manager.update_credentials(repo_id, json.dumps(credentials_data))
    else:
        secrets_manager.add_credentials(repo_id, json.dumps(credentials_data))


def _get_repo_head(storage: Storage, repo_id: str) -> Optional[RepoHead]:
    repo_head_prefix = _get_repo_head_filename_prefix(repo_id)
    repo_heads_keys = storage.list_objects(repo_head_prefix)
    if len(repo_heads_keys) == 0:
        return None
    return _parse_repo_head_filename(repo_heads_keys[0])


def _create_or_update_repo_head(storage: Storage, repo_head: RepoHead):
    _delete_repo_head(storage=storage, repo_id=repo_head.repo_id)
    repo_head_prefix = _get_repo_head_filename_prefix(repo_head.repo_id)
    repo_head_key = f"{repo_head_prefix}{repo_head.last_run_at or ''};{repo_head.tags_count};"
    repo_head_key += repo_head.repo_info.head_key
    storage.put_object(key=repo_head_key, content="")


def _delete_repo_head(storage: Storage, repo_id: str):
    repo_head_prefix = _get_repo_head_filename_prefix(repo_id)
    repo_heads_keys = storage.list_objects(repo_head_prefix)
    for repo_head_key in repo_heads_keys:
        storage.delete_object(repo_head_key)


def _get_repo_heads_prefix() -> str:
    return "repos/l;"


def _get_repo_head_filename_prefix(repo_id: str) -> str:
    return f"{_get_repo_heads_prefix()}{repo_id};"


def _parse_repo_head_filename(repo_head_filepath: str) -> Optional[RepoHead]:
    repo_heads_prefix = _get_repo_heads_prefix()
    r = repo_head_re.search(repo_head_filepath[len(repo_heads_prefix) :])
    if r is None:
        return r
    repo_id, last_run_at, tags_count, repo_type, repo_info = r.groups()

    if repo_type == "remote":
        repo_host_name, repo_port, repo_user_name, repo_name = repo_info.split(",")
        repo_info = RemoteRepoInfo(
            repo_host_name=repo_host_name,
            repo_port=repo_port or None,
            repo_user_name=repo_user_name,
            repo_name=repo_name,
        )
    elif repo_type == "local":
        repo_dir = repo_info
        repo_info = LocalRepoInfo(repo_dir=unescape_head(repo_dir))
    return RepoHead(
        repo_id=repo_id,
        repo_info=repo_info,
        last_run_at=int(last_run_at) if last_run_at else None,
        tags_count=int(tags_count),
    )
