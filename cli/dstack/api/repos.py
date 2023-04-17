import os
import tempfile
from typing import Optional

import git
import yaml

from dstack.core.repo import RemoteRepoCredentials, RemoteRepoData, RepoProtocol
from dstack.utils.common import PathLike
from dstack.utils.ssh import get_host_config

gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")
default_ssh_key = os.path.expanduser("~/.ssh/id_rsa")


def read_ssh_key(path: PathLike) -> str:
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise  # todo custom exception


def get_local_repo_credentials(
    hostname: str,
    identity_file: Optional[PathLike] = None,
    oauth_token: Optional[str] = None,
) -> RemoteRepoCredentials:
    # user provided ssh key
    if identity_file is not None:
        return RemoteRepoCredentials(
            protocol=RepoProtocol.SSH, private_key=read_ssh_key(identity_file), oauth_token=None
        )
    # user provided oauth token
    if oauth_token is not None:
        return RemoteRepoCredentials(
            protocol=RepoProtocol.HTTPS, oauth_token=oauth_token, private_key=None
        )
    # key from ssh config
    identities = get_host_config(hostname).get("identityfile")
    if identities:
        return RemoteRepoCredentials(
            protocol=RepoProtocol.SSH, private_key=read_ssh_key(identities[0]), oauth_token=None
        )
    # token from gh config
    if os.path.exists(gh_config_path):
        with open(gh_config_path, "r") as f:
            gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
        oauth_token = gh_hosts.get(hostname, {}).get("oauth_token")
        if oauth_token:
            return RemoteRepoCredentials(
                protocol=RepoProtocol.HTTPS, oauth_token=oauth_token, private_key=None
            )
    # default user key
    if os.path.exists(default_ssh_key):
        return RemoteRepoCredentials(
            protocol=RepoProtocol.SSH, private_key=read_ssh_key(default_ssh_key), oauth_token=None
        )
    # no auth
    return RemoteRepoCredentials(protocol=RepoProtocol.HTTPS, oauth_token=None, private_key=None)


def test_repo_credentials(repo_data: RemoteRepoData, repo_credentials: RemoteRepoCredentials):
    if repo_credentials.protocol == RepoProtocol.HTTPS:
        return git.cmd.Git().ls_remote(
            f"https://"
            f"{(repo_credentials.oauth_token + '@') if repo_credentials.oauth_token else ''}"
            f"{repo_data.path(sep='/')}.git"
        )
    elif repo_credentials.protocol == RepoProtocol.SSH:
        with tempfile.NamedTemporaryFile(mode="w+b") as f:
            if repo_credentials.private_key is not None:
                f.write(repo_credentials.private_key.encode())
                f.seek(0)
            git_ssh_command = f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={f.name}"
            if repo_data.repo_port:
                url = f"ssh@{repo_data.path(sep='/')}.git"
            else:
                url = f"git@{repo_data.repo_host_name}:{repo_data.repo_user_name}/{repo_data.repo_name}.git"
            return git.cmd.Git().ls_remote(url, env=dict(GIT_SSH_COMMAND=git_ssh_command))
