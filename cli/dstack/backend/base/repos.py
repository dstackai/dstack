import json
from typing import List, Optional

from dstack.backend.base.secrets import SecretsManager
from dstack.backend.base.storage import Storage
from dstack.core.repo import RepoAddress, RepoCredentials, RepoHead, RepoProtocol


def get_repo_head(storage: Storage, repo_address: RepoAddress) -> Optional[RepoHead]:
    repo_head_prefix = _get_repo_head_filename_prefix(repo_address)
    repo_heads_keys = storage.list_objects(repo_head_prefix)
    if len(repo_heads_keys) == 0:
        return None
    repo_head_key = repo_heads_keys[0]
    last_run_at, tags_count = repo_head_key[len(repo_head_prefix) :].split(";")
    return RepoHead(
        repo_host_name=repo_address.repo_host_name,
        repo_port=repo_address.repo_port,
        repo_user_name=repo_address.repo_user_name,
        repo_name=repo_address.repo_name,
        last_run_at=int(last_run_at) if last_run_at else None,
        tags_count=int(tags_count),
    )


def list_repo_heads(storage: Storage) -> List[RepoHead]:
    repo_heads_prefix = _get_repo_heads_prefix()
    repo_heads_keys = storage.list_objects(repo_heads_prefix)
    repo_heads = []
    for repo_head_key in repo_heads_keys:
        tokens = repo_head_key[len(repo_heads_prefix) :].split(";")
        # Skipt legacy repo heads
        if len(tokens) != 3:
            continue
        repo_str, last_run_at, tags_count = tokens
        repo_host_port, repo_user_name, repo_name = repo_str.split(",")
        t = repo_host_port.split(":")
        repo_host_name = t[0]
        repo_port = t[1] if len(t) > 1 else None
        repo_heads.append(
            RepoHead(
                repo_host_name=repo_host_name,
                repo_port=repo_port,
                repo_user_name=repo_user_name,
                repo_name=repo_name,
                last_run_at=int(last_run_at) if last_run_at else None,
                tags_count=int(tags_count),
            )
        )
    return repo_heads


def update_repo_last_run_at(storage: Storage, repo_address: RepoAddress, last_run_at: int):
    repo_head = get_repo_head(storage, repo_address)
    if repo_head is None:
        repo_head = RepoHead(
            repo_host_name=repo_address.repo_host_name,
            repo_port=repo_address.repo_port,
            repo_user_name=repo_address.repo_user_name,
            repo_name=repo_address.repo_name,
            last_run_at=None,
            tags_count=0,
        )
    repo_head.last_run_at = last_run_at
    _create_or_update_repo_head(storage, repo_head)


def delete_repo(storage: Storage, repo_address: RepoAddress):
    _delete_repo_head(storage, repo_address)


def get_repo_credentials(
    secrets_manager: SecretsManager, repo_address: RepoAddress
) -> Optional[RepoCredentials]:
    credentials_value = secrets_manager.get_credentials(repo_address)
    if credentials_value is None:
        return None
    credentials_data = json.loads(credentials_value)
    return RepoCredentials(**credentials_data)


def save_repo_credentials(
    secrets_manager: SecretsManager,
    repo_address: RepoAddress,
    repo_credentials: RepoCredentials,
):
    credentials_data = {"protocol": repo_credentials.protocol.value}
    if repo_credentials.protocol == RepoProtocol.HTTPS and repo_credentials.oauth_token:
        credentials_data["oauth_token"] = repo_credentials.oauth_token
    elif repo_credentials.protocol == RepoProtocol.SSH:
        if repo_credentials.private_key:
            credentials_data["private_key"] = repo_credentials.private_key
        else:
            raise Exception("No private key is specified")

    credentials_value = secrets_manager.get_credentials(repo_address)
    if credentials_value is not None:
        secrets_manager.update_credentials(repo_address, json.dumps(credentials_data))
    else:
        secrets_manager.add_credentials(repo_address, json.dumps(credentials_data))


def _create_or_update_repo_head(storage: Storage, repo_head: RepoHead):
    _delete_repo_head(storage=storage, repo_address=RepoAddress.parse_obj(repo_head))
    repo_head_prefix = _get_repo_head_filename_prefix(
        repo_address=RepoAddress.parse_obj(repo_head)
    )
    repo_head_key = (
        f"{repo_head_prefix}" f"{repo_head.last_run_at or ''};" f"{repo_head.tags_count}"
    )
    storage.put_object(key=repo_head_key, content="")


def _delete_repo_head(storage: Storage, repo_address: RepoAddress):
    repo_head_prefix = _get_repo_head_filename_prefix(repo_address)
    repo_heads_keys = storage.list_objects(repo_head_prefix)
    for repo_head_key in repo_heads_keys:
        storage.delete_object(repo_head_key)


def _get_repo_heads_prefix() -> str:
    return "repos/l;"


def _get_repo_head_filename_prefix(repo_address: RepoAddress) -> str:
    return f"repos/l;{repo_address.path(delimiter=',')};"
