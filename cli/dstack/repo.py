import os
import sys
from enum import Enum
from typing import Optional

import git
import giturlparse
import yaml
from git import Repo as GitRepo
from paramiko.config import SSHConfig

from dstack.util import _quoted, _quoted_masked


class RepoProtocol(Enum):
    HTTPS = "https"
    SSH = "ssh"


class RepoCredentials:
    def __init__(self, protocol: RepoProtocol, private_key: Optional[str], oauth_token: Optional[str]):
        self.protocol = protocol
        self.private_key = private_key
        self.oauth_token = oauth_token

    def __str__(self) -> str:
        return f'RepoCredentials(protocol=RepoProtocol.{self.protocol.name}, ' \
               f'private_key_length={len(self.private_key) if self.private_key else None}, ' \
               f'oauth_token={_quoted_masked(self.oauth_token)})'


class RepoAddress:
    def __init__(self, repo_host_name: str, repo_port: Optional[int], repo_user_name: str, repo_name: str) -> None:
        self.repo_host_name = repo_host_name
        self.repo_port = repo_port
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name

    def __str__(self) -> str:
        return f'RepoAddress(repo_host_name="{self.repo_host_name}", ' \
               f'repo_port={_quoted(self.repo_port)}", ' \
               f'repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}")'


class RepoData(RepoAddress):
    def __init__(self, repo_host_name: str, repo_port: Optional[int], repo_user_name: str, repo_name: str,
                 repo_branch: str, repo_hash: str, repo_diff: Optional[str]):
        super().__init__(repo_host_name, repo_port, repo_user_name, repo_name)
        self.repo_host_name = repo_host_name
        self.repo_port = repo_port
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.repo_branch = repo_branch
        self.repo_hash = repo_hash
        self.repo_diff = repo_diff

    def __str__(self) -> str:
        return f'RepoData(repo_host_name="{self.repo_host_name}", ' \
               f'repo_port={_quoted(self.repo_port)}", ' \
               f'repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'repo_branch="{self.repo_branch}", ' \
               f'repo_hash="{self.repo_hash}", ' \
               f'repo_diff_length={len(self.repo_diff) if self.repo_diff else None})'


class LocalRepoData(RepoData):
    def __init__(self, repo_host_name: str, repo_port: Optional[int], repo_user_name: str, repo_name: str,
                 repo_branch: str, repo_hash: str, repo_diff: Optional[str], protocol: RepoProtocol,
                 identity_file: Optional[str], oauth_token: Optional[str],
                 local_repo_user_name: str, local_repo_user_email: Optional[str]):
        super().__init__(repo_host_name, repo_port, repo_user_name, repo_name, repo_branch, repo_hash, repo_diff)
        self.protocol = protocol
        self.identity_file = identity_file
        self.oauth_token = oauth_token
        self.local_repo_user_name = local_repo_user_name
        self.local_repo_user_email = local_repo_user_email

    def __str__(self) -> str:
        return f'LocalRepoData(repo_host_name="{self.repo_host_name}", ' \
               f'repo_port={_quoted(self.repo_port)}", ' \
               f'repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'repo_branch="{self.repo_branch}", ' \
               f'repo_hash="{self.repo_hash}", ' \
               f'repo_diff_length={len(self.repo_diff) if self.repo_diff else None}, ' \
               f'protocol=RepoProtocol.{self.protocol.name}, ' \
               f'identity_file={_quoted(self.identity_file)}, ' \
               f'oauth_token={_quoted_masked(self.oauth_token)},' \
               f'local_repo_user_name="{self.local_repo_user_name}", ' \
               f'local_repo_user_email={_quoted(self.local_repo_user_email)})'

    def ls_remote(self) -> str:
        if self.protocol == RepoProtocol.HTTPS:
            return git.cmd.Git().ls_remote(f"https://"
                                           f"{(self.oauth_token + '@') if self.oauth_token else ''}"
                                           f"{_repo_address_path(self)}.git")
        else:
            if self.identity_file:
                git_ssh_command = f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={self.identity_file}"
                if self.repo_port:
                    url = f"ssh@{_repo_address_path(self)}.git"
                else:
                    url = f"git@{self.repo_host_name}:{self.repo_user_name}/{self.repo_name}.git"
                return git.cmd.Git().ls_remote(url, env=dict(GIT_SSH_COMMAND=git_ssh_command))
            else:
                raise Exception("No identity file is specified")

    def repo_credentials(self) -> RepoCredentials:
        if self.protocol == RepoProtocol.HTTPS:
            return RepoCredentials(self.protocol, private_key=None, oauth_token=self.oauth_token)
        elif self.identity_file:
            with open(self.identity_file, "r") as f:
                return RepoCredentials(self.protocol, private_key=f.read(), oauth_token=None)
        else:
            raise Exception("No identity file is specified")


def load_repo_data(oauth_token: Optional[str] = None, identity_file: Optional[str] = None) -> LocalRepoData:
    # TODO: Allow to override the current working directory, e.g. via --dir
    cwd = os.getcwd()
    repo = GitRepo(cwd)
    tracking_branch = repo.active_branch.tracking_branch()
    if tracking_branch:
        repo_branch = tracking_branch.remote_head
        remote_name = tracking_branch.remote_name
        repo_hash = tracking_branch.commit.hexsha
        repo_url = repo.remote(remote_name).url

        local_repo_user_name = repo.config_reader().get_value("user", "name")
        local_repo_user_email = repo.config_reader().get_value("user", "email", "") or None

        repo_url_parsed = giturlparse.parse(repo_url)
        repo_oauth_token = oauth_token
        repo_identity_file = identity_file
        repo_host_name = repo_url_parsed.resource
        repo_port = repo_url_parsed.port
        if repo_url_parsed.protocol == "ssh":
            ssh_config_path = os.path.expanduser('~/.ssh/config')
            if os.path.exists(ssh_config_path):
                with open(ssh_config_path, "r") as f:
                    config = SSHConfig()
                    config.parse(f)
                    c = config.lookup(repo_url_parsed.resource)
                    repo_host_name = c["hostname"]
                    repo_port = c["port"] if c.get("port") else repo_port
                    if not identity_file:
                        i = c.get("identityfile")
                        repo_identity_file = i[0] if i else None
                    # TODO: Detect and pass private key too
        elif not oauth_token:
            gh_config_path = os.path.expanduser('~/.config/gh/hosts.yml')
            if os.path.exists(gh_config_path):
                with open(gh_config_path, "r") as f:
                    hosts_data = yaml.load(f, Loader=yaml.FullLoader)
                    if repo_host_name in hosts_data:
                        repo_oauth_token = hosts_data[repo_host_name].get("oauth_token")
        # TODO: Doesn't support unstaged changes
        repo_diff = repo.git.diff(repo_hash)
        return LocalRepoData(repo_host_name, repo_port, repo_url_parsed.owner, repo_url_parsed.name, repo_branch,
                             repo_hash, repo_diff,
                             RepoProtocol.HTTPS if repo_url_parsed.protocol == "https" else RepoProtocol.SSH,
                             repo_identity_file or os.path.expanduser('~/.ssh/id_rsa'), repo_oauth_token,
                             local_repo_user_name, local_repo_user_email)
    else:
        sys.exit(f"No tracked branch configured for branch {repo.active_branch.name}")


def _repo_address_path(repo_address: RepoAddress, delimiter: str = '/'):
    return f"{repo_address.repo_host_name}" \
           f"{(':' + str(repo_address.repo_port)) if repo_address.repo_port else ''}{delimiter}" \
           f"{repo_address.repo_user_name}{delimiter}{repo_address.repo_name}"
