import os
from pathlib import Path
from typing import Optional

import giturlparse

from dstack._internal.api.repos import get_local_repo_credentials
from dstack._internal.cli.errors import CLIError
from dstack._internal.cli.utils.config import config
from dstack._internal.core.repo import LocalRepo, RemoteRepo
from dstack._internal.core.userconfig import RepoUserConfig
from dstack._internal.utils.crypto import generate_rsa_key_pair
from dstack.api.hub import HubClient


def _get_ssh_keypair(
    key_path: Optional[Path], dstack_key_path: Optional[Path] = None
) -> Optional[str]:
    """Returns path to the private key if keypair exists"""
    if key_path is not None:
        key_path = key_path.expanduser().resolve()
        pub_key = (
            key_path
            if key_path.suffix == ".pub"
            else key_path.with_suffix(key_path.suffix + ".pub")
        )
        private_key = pub_key.with_suffix("")
        if pub_key.exists() and private_key.exists():
            return str(private_key)
        raise CLIError(
            f"Make sure valid keypair exists: {private_key}(.pub) and rerun `dstack init`"
        )

    if dstack_key_path is None:
        return None
    if not dstack_key_path.exists():
        generate_rsa_key_pair(private_key_path=dstack_key_path)
    return str(dstack_key_path)


def init_repo(
    hub_client: HubClient,
    git_identity_file: Optional[str] = None,
    oauth_token: Optional[str] = None,
    ssh_identity_file: Optional[str] = None,
):
    if isinstance(hub_client.repo, RemoteRepo):
        repo_dir = hub_client.repo.local_repo_dir
        repo_credentials = get_local_repo_credentials(
            repo_data=hub_client.repo.repo_data,
            identity_file=os.path.expanduser(git_identity_file) if git_identity_file else None,
            oauth_token=oauth_token,
            original_hostname=giturlparse.parse(hub_client.repo.repo_url).resource,
        )
    elif isinstance(hub_client.repo, LocalRepo):
        repo_dir = hub_client.repo.repo_data.repo_dir
        repo_credentials = None
    else:
        raise TypeError(f"Unknown repo type: {type(hub_client.repo)}")

    config.save_repo_user_config(
        repo_dir,
        RepoUserConfig(
            repo_id=hub_client.repo.repo_ref.repo_id,
            repo_type=hub_client.repo.repo_data.repo_type,
            ssh_key_path=_get_ssh_keypair(
                ssh_identity_file,
                dstack_key_path=config.dstack_key_path(Path.cwd()),
            ),
        ),
    )
    backends = hub_client.list_backends()
    if len(backends) == 0:
        settings_url = f"{hub_client.client_config.url}/projects/{hub_client.project}/settings"
        raise CLIError(f"No backends configured. Add backends at {settings_url}")
    if repo_credentials is not None:
        hub_client.save_repo_credentials(repo_credentials)
