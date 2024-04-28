import os
from pathlib import Path
from typing import Optional, Union

import git
import requests
import yaml
from git.exc import GitCommandError

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.config import RepoConfig
from dstack._internal.core.models.repos import (
    LocalRepo,
    RemoteRepo,
    RemoteRepoCreds,
    RemoteRunRepoData,
)
from dstack._internal.core.models.repos.base import RepoProtocol
from dstack._internal.utils.path import PathLike
from dstack._internal.utils.ssh import (
    get_host_config,
    make_ssh_command_for_git,
    try_ssh_key_passphrase,
)

gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")
default_ssh_key = os.path.expanduser("~/.ssh/id_rsa")


class InvalidRepoCredentialsError(DstackError):
    pass


def get_local_repo_credentials(
    repo_data: RemoteRunRepoData,
    identity_file: Optional[PathLike] = None,
    oauth_token: Optional[str] = None,
    original_hostname: Optional[str] = None,
) -> RemoteRepoCreds:
    url = repo_data.make_url(RepoProtocol.HTTPS)  # no auth
    r = requests.get(f"{url}/info/refs?service=git-upload-pack", timeout=10)
    if r.status_code == 200:
        return RemoteRepoCreds(protocol=RepoProtocol.HTTPS, private_key=None, oauth_token=None)

    if identity_file is not None:  # must fail if key is invalid
        identity_file = os.path.expanduser(identity_file)
        try:  # user provided ssh key
            return check_remote_repo_credentials(
                repo_data, RepoProtocol.SSH, identity_file=identity_file
            )
        except GitCommandError:
            url = repo_data.make_url(RepoProtocol.SSH)
            raise InvalidRepoCredentialsError(
                f"Can't access `{url}` using the `{identity_file}` private SSH key"
            )

    if oauth_token is not None:
        try:  # user provided oauth token
            return check_remote_repo_credentials(
                repo_data, RepoProtocol.HTTPS, oauth_token=oauth_token
            )
        except GitCommandError:
            url = repo_data.make_url(RepoProtocol.SSH, oauth_token)
            masked = len(oauth_token[:-4]) * "*" + oauth_token[-4:]
            raise InvalidRepoCredentialsError(f"Can't access `{url}` using the `{masked}` token")

    identities = get_host_config(original_hostname or repo_data.repo_host_name).get("identityfile")
    if identities:  # must fail if key is invalid
        try:  # key from ssh config
            return check_remote_repo_credentials(
                repo_data, RepoProtocol.SSH, identity_file=identities[0]
            )
        except GitCommandError:
            url = repo_data.make_url(RepoProtocol.SSH, oauth_token)
            raise InvalidRepoCredentialsError(
                f"Can't access `{url}` using the `{identities[0]}` SSH private key"
            )

    if os.path.exists(gh_config_path):
        with open(gh_config_path, "r") as f:
            gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
        oauth_token = gh_hosts.get(repo_data.repo_host_name, {}).get("oauth_token")
        if oauth_token is not None:
            try:  # token from gh config
                return check_remote_repo_credentials(
                    repo_data, RepoProtocol.HTTPS, oauth_token=oauth_token
                )
            except GitCommandError:
                pass

    if os.path.exists(default_ssh_key):
        try:  # default user key
            return check_remote_repo_credentials(
                repo_data, RepoProtocol.SSH, identity_file=default_ssh_key
            )
        except GitCommandError:
            pass

    raise InvalidRepoCredentialsError(
        "No valid default Git credentials found: ensure passing a valid `--token` or `--git-identity` to `dstack init`."
    )


def check_remote_repo_credentials(
    repo_data: RemoteRunRepoData,
    protocol: RepoProtocol,
    *,
    identity_file: Optional[PathLike] = None,
    oauth_token: Optional[str] = None,
) -> RemoteRepoCreds:
    url = repo_data.make_url(protocol, oauth_token)
    if protocol == RepoProtocol.HTTPS:
        git.cmd.Git().ls_remote(url, env=dict(GIT_TERMINAL_PROMPT="0"))
        return RemoteRepoCreds(protocol=protocol, oauth_token=oauth_token, private_key=None)
    elif protocol == RepoProtocol.SSH:
        if not Path(identity_file).exists():
            raise InvalidRepoCredentialsError(f"The {identity_file} private SSH key doesn't exist")
        if not os.access(identity_file, os.R_OK):
            raise InvalidRepoCredentialsError(f"Can't access the {identity_file} private SSH key")
        if not try_ssh_key_passphrase(identity_file):
            raise InvalidRepoCredentialsError(
                f"Can't access `{url}`: ensure the `{identity_file}` private SSH key is valid and passphrase-free"
            )
        with open(identity_file, "r") as f:
            private_key = f.read()
        git.cmd.Git().ls_remote(
            url, env=dict(GIT_SSH_COMMAND=make_ssh_command_for_git(identity_file))
        )
        return RemoteRepoCreds(protocol=protocol, private_key=private_key, oauth_token=None)


def load_repo(config: RepoConfig) -> Union[RemoteRepo, LocalRepo]:
    if config.repo_type == "remote":
        return RemoteRepo(repo_id=config.repo_id, local_repo_dir=config.path)
    elif config.repo_type == "local":
        return LocalRepo(repo_id=config.repo_id, repo_dir=config.path)
    raise TypeError(f"Unknown repo_type: {config.repo_type}")
