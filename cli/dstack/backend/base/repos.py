import json
from typing import List, Optional

from dstack.backend.base.secrets import SecretsManager
from dstack.backend.base.storage import Storage
from dstack.core.repo import (
    RemoteRepoCredentials,
    RemoteRepoInfo,
    RepoHead,
    RepoProtocol,
    RepoRef,
    RepoSpec,
)


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
    repo_head = _get_repo_head(storage, repo_spec.repo_ref)
    if repo_head is None:
        repo_head = RepoHead(
            repo_id=repo_spec.repo_ref.repo_id,
            repo_info=RemoteRepoInfo(
                repo_host_name=repo_spec.repo_data.repo_host_name,
                repo_port=repo_spec.repo_data.repo_port,
                repo_user_name=repo_spec.repo_data.repo_user_name,
                repo_name=repo_spec.repo_data.repo_name,
            ),
        )
    repo_head.last_run_at = last_run_at
    _create_or_update_repo_head(storage, repo_head)


def delete_repo(storage: Storage, repo_ref: RepoRef):
    _delete_repo_head(storage, repo_ref)


def get_repo_credentials(secrets_manager: SecretsManager) -> Optional[RemoteRepoCredentials]:
    credentials_value = secrets_manager.get_credentials()
    if credentials_value is None:
        return None
    credentials_data = json.loads(credentials_value)
    return RemoteRepoCredentials(**credentials_data)


def save_repo_credentials(
    secrets_manager: SecretsManager, repo_credentials: RemoteRepoCredentials
):
    credentials_data = {"protocol": repo_credentials.protocol.value}
    if repo_credentials.protocol == RepoProtocol.HTTPS and repo_credentials.oauth_token:
        credentials_data["oauth_token"] = repo_credentials.oauth_token
    elif repo_credentials.protocol == RepoProtocol.SSH:
        if repo_credentials.private_key:
            credentials_data["private_key"] = repo_credentials.private_key
        else:
            raise Exception("No private key is specified")

    credentials_value = secrets_manager.get_credentials()
    if credentials_value is not None:
        secrets_manager.update_credentials(json.dumps(credentials_data))
    else:
        secrets_manager.add_credentials(json.dumps(credentials_data))


def _get_repo_head(storage: Storage, repo_ref: RepoRef) -> Optional[RepoHead]:
    repo_head_prefix = _get_repo_head_filename_prefix(repo_ref)
    repo_heads_keys = storage.list_objects(repo_head_prefix)
    if len(repo_heads_keys) == 0:
        return None
    return _parse_repo_head_filename(repo_heads_keys[0])


def _create_or_update_repo_head(storage: Storage, repo_head: RepoHead):
    _delete_repo_head(storage=storage, repo_ref=repo_head)
    repo_head_prefix = _get_repo_head_filename_prefix(repo_ref=repo_head)
    repo_head_key = f"{repo_head_prefix}{repo_head.last_run_at or ''};{repo_head.tags_count};"
    repo_info = repo_head.repo_info
    repo_head_key += f"{repo_info.repo_host_name},{repo_info.repo_port or ''},{repo_info.repo_user_name},{repo_info.repo_name}"
    storage.put_object(key=repo_head_key, content="")


def _delete_repo_head(storage: Storage, repo_ref: RepoRef):
    repo_head_prefix = _get_repo_head_filename_prefix(repo_ref)
    repo_heads_keys = storage.list_objects(repo_head_prefix)
    for repo_head_key in repo_heads_keys:
        storage.delete_object(repo_head_key)


def _get_repo_heads_prefix() -> str:
    return "repos/l;"


def _get_repo_head_filename_prefix(repo_ref: RepoRef) -> str:
    return f"{_get_repo_heads_prefix()}{repo_ref.repo_type};{repo_ref.repo_id};"


def _parse_repo_head_filename(repo_head_filepath: str) -> Optional[RepoHead]:
    repo_heads_prefix = _get_repo_heads_prefix()
    try:
        repo_type, repo_id, last_run_at, tags_count, repo_info = repo_head_filepath[
            len(repo_heads_prefix) :
        ].split(";")
        repo_host_name, repo_port, repo_user_name, repo_name = repo_info.split(",")
    except ValueError:
        # Legacy repo head
        return None
    repo_info = RemoteRepoInfo(
        repo_host_name=repo_host_name,
        repo_port=repo_port or None,
        repo_user_name=repo_user_name,
        repo_name=repo_name,
    )
    return RepoHead(
        repo_id=repo_id,
        repo_info=repo_info,
        last_run_at=int(last_run_at) if last_run_at else None,
        tags_count=int(tags_count),
    )
