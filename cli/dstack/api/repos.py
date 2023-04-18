import os
from typing import Optional

import git
import yaml
from git.exc import GitCommandError

from dstack.core.repo import RemoteRepoCredentials, RemoteRepoData, RepoProtocol
from dstack.utils.common import PathLike
from dstack.utils.ssh import get_host_config

gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")
default_ssh_key = os.path.expanduser("~/.ssh/id_rsa")


def get_local_repo_credentials(
    repo_data: RemoteRepoData,
    identity_file: Optional[PathLike] = None,
    oauth_token: Optional[str] = None,
    original_hostname: Optional[str] = None,
) -> RemoteRepoCredentials:
    try:  # no auth
        return test_remote_repo_credentials(repo_data, RepoProtocol.HTTPS)
    except GitCommandError:
        pass

    if identity_file is not None:  # must fail if key is invalid
        try:  # user provided ssh key
            return test_remote_repo_credentials(
                repo_data, RepoProtocol.SSH, identity_file=identity_file
            )
        except GitCommandError:
            pass

    if oauth_token is not None:
        try:  # user provided oauth token
            return test_remote_repo_credentials(
                repo_data, RepoProtocol.HTTPS, oauth_token=oauth_token
            )
        except GitCommandError:
            pass

    identities = get_host_config(original_hostname or repo_data.repo_host_name).get("identityfile")
    if identities:  # must fail if key is invalid
        try:  # key from ssh config
            return test_remote_repo_credentials(
                repo_data, RepoProtocol.SSH, identity_file=identities[0]
            )
        except GitCommandError:
            pass

    if os.path.exists(gh_config_path):
        with open(gh_config_path, "r") as f:
            gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
        oauth_token = gh_hosts.get(repo_data.repo_host_name, {}).get("oauth_token")
        if oauth_token is not None:
            try:  # token from gh config
                return test_remote_repo_credentials(
                    repo_data, RepoProtocol.HTTPS, oauth_token=oauth_token
                )
            except GitCommandError:
                pass

    if os.path.exists(default_ssh_key):
        try:  # default user key
            return test_remote_repo_credentials(
                repo_data, RepoProtocol.SSH, identity_file=default_ssh_key
            )
        except GitCommandError:
            pass

    # todo raise?


def test_remote_repo_credentials(
    repo_data: RemoteRepoData,
    protocol: RepoProtocol,
    *,
    identity_file: Optional[PathLike] = None,
    oauth_token: Optional[str] = None,
) -> RemoteRepoCredentials:
    if protocol == RepoProtocol.HTTPS:
        git.cmd.Git().ls_remote(
            f"https://"
            f"{(oauth_token + '@') if oauth_token else ''}"
            f"{repo_data.path(sep='/')}.git",
            env=dict(GIT_TERMINAL_PROMPT="0"),
        )
        return RemoteRepoCredentials(protocol=protocol, oauth_token=oauth_token, private_key=None)
    elif protocol == RepoProtocol.SSH:
        if repo_data.repo_port:
            url = f"ssh@{repo_data.path(sep='/')}.git"
        else:
            url = f"git@{repo_data.repo_host_name}:{repo_data.repo_user_name}/{repo_data.repo_name}.git"

        with open(identity_file, "r") as f:
            private_key = f.read()
        git.cmd.Git().ls_remote(url, env=dict(GIT_SSH_COMMAND=_make_ssh_command(identity_file)))
        # todo: detect if key requires passphrase
        return RemoteRepoCredentials(protocol=protocol, private_key=private_key, oauth_token=None)


def _make_ssh_command(identity_file: PathLike) -> str:
    return f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={identity_file}"
