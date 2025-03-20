import os
from pathlib import Path
from typing import Optional, Union

import git
import requests
import yaml
from git.exc import GitCommandError

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.config import RepoConfig
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo, RemoteRepoCreds
from dstack._internal.core.models.repos.remote import GitRepoURL
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike
from dstack._internal.utils.ssh import (
    get_host_config,
    make_ssh_command_for_git,
    try_ssh_key_passphrase,
)

logger = get_logger(__name__)

gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")
default_ssh_key = os.path.expanduser("~/.ssh/id_rsa")


class InvalidRepoCredentialsError(DstackError):
    pass


def get_local_repo_credentials(
    repo_url: str,
    identity_file: Optional[PathLike] = None,
    oauth_token: Optional[str] = None,
) -> RemoteRepoCreds:
    url = GitRepoURL.parse(repo_url, get_ssh_config=get_host_config)

    # no auth
    r = requests.get(f"{url.as_https()}/info/refs?service=git-upload-pack", timeout=10)
    if r.status_code == 200:
        return RemoteRepoCreds(
            clone_url=url.as_https(),
            private_key=None,
            oauth_token=None,
        )

    # user-provided ssh key
    if identity_file is not None:
        identity_file = os.path.expanduser(identity_file)
        return check_remote_repo_credentials_ssh(url, identity_file)

    # user-provided oauth token
    if oauth_token is not None:
        return check_remote_repo_credentials_https(url, oauth_token)

    # key from ssh config
    identities = get_host_config(url.original_host).get("identityfile")
    if identities:
        return check_remote_repo_credentials_ssh(url, identities[0])

    # token from gh config
    if os.path.exists(gh_config_path):
        with open(gh_config_path, "r") as f:
            gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
        oauth_token = gh_hosts.get(url.host, {}).get("oauth_token")
        if oauth_token is not None:
            try:
                return check_remote_repo_credentials_https(url, oauth_token)
            except InvalidRepoCredentialsError:
                pass

    # default user key
    if os.path.exists(default_ssh_key):
        try:
            return check_remote_repo_credentials_ssh(url, default_ssh_key)
        except InvalidRepoCredentialsError:
            pass

    raise InvalidRepoCredentialsError(
        "No valid default Git credentials found. Pass valid `--token` or `--git-identity`."
    )


def check_remote_repo_credentials_https(url: GitRepoURL, oauth_token: str) -> RemoteRepoCreds:
    try:
        git.cmd.Git().ls_remote(url.as_https(oauth_token), env=dict(GIT_TERMINAL_PROMPT="0"))
    except GitCommandError:
        masked = len(oauth_token[:-4]) * "*" + oauth_token[-4:]
        raise InvalidRepoCredentialsError(
            f"Can't access `{url.as_https()}` using the `{masked}` token"
        )
    return RemoteRepoCreds(
        clone_url=url.as_https(),
        oauth_token=oauth_token,
        private_key=None,
    )


def check_remote_repo_credentials_ssh(url: GitRepoURL, identity_file: PathLike) -> RemoteRepoCreds:
    if not Path(identity_file).exists():
        raise InvalidRepoCredentialsError(f"The {identity_file} private SSH key doesn't exist")
    if not os.access(identity_file, os.R_OK):
        raise InvalidRepoCredentialsError(f"Can't access the {identity_file} private SSH key")
    if not try_ssh_key_passphrase(identity_file):
        raise InvalidRepoCredentialsError(
            f"Cannot use the `{identity_file}` private SSH key. "
            "Ensure that it is valid and passphrase-free"
        )
    with open(identity_file, "r") as f:
        private_key = f.read()

    try:
        git.cmd.Git().ls_remote(
            url.as_ssh(), env=dict(GIT_SSH_COMMAND=make_ssh_command_for_git(identity_file))
        )
    except GitCommandError:
        raise InvalidRepoCredentialsError(
            f"Can't access `{url.as_ssh()}` using the `{identity_file}` private SSH key"
        )

    return RemoteRepoCreds(
        clone_url=url.as_ssh(),
        private_key=private_key,
        oauth_token=None,
    )


def get_default_branch(remote_url: str) -> Optional[str]:
    """
    Get the default branch of a remote Git repository.
    """
    try:
        output = git.cmd.Git().ls_remote("--symref", remote_url, "HEAD")
        for line in output.splitlines():
            if line.startswith("ref:"):
                return line.split()[1].split("/")[-1]
    except Exception as e:
        logger.debug("Failed to get remote repo default branch: %s", repr(e))
    return None


def load_repo(config: RepoConfig) -> Union[RemoteRepo, LocalRepo]:
    if config.repo_type == "remote":
        return RemoteRepo(repo_id=config.repo_id, local_repo_dir=config.path)
    elif config.repo_type == "local":
        return LocalRepo(repo_id=config.repo_id, repo_dir=config.path)
    raise TypeError(f"Unknown repo_type: {config.repo_type}")
