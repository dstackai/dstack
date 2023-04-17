import os
import tempfile
from typing import Optional

import git
import yaml

from dstack.core.repo import RemoteRepoData, RepoCredentials, RepoProtocol
from dstack.utils.common import PathLike
from dstack.utils.ssh import get_host_config

gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")


def get_local_repo_credentials(
    repo_data: RemoteRepoData,
    identity_file: Optional[PathLike] = None,
    oauth_token: Optional[str] = None,
) -> RepoCredentials:
    private_key = None
    if repo_data.repo_protocol == "ssh":
        if identity_file is None:
            host_config = get_host_config(repo_data.repo_host_name)
            identities = host_config.get("identityfile")
            if identities:
                identity_file = os.path.expanduser(identities[0])
            else:
                identity_file = os.path.expanduser("~/.ssh/id_rsa")
            # TODO: Detect and pass private key too ?
        if os.path.exists(identity_file):
            with open(identity_file, "r") as f:
                private_key = f.read()
    elif repo_data.repo_protocol == "https":
        if oauth_token is None:
            if os.path.exists(gh_config_path):
                with open(gh_config_path, "r") as f:
                    gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
                oauth_token = gh_hosts.get(repo_data.repo_host_name, {}).get("oauth_token")
    return RepoCredentials(
        protocol=RepoProtocol[repo_data.repo_protocol.upper()],
        private_key=private_key,
        oauth_token=oauth_token,
    )


def test_repo_credentials(repo_data: RemoteRepoData, repo_credentials: RepoCredentials):
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
