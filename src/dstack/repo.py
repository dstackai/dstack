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


class RepoData:
    def __init__(self, repo_user_name: str, repo_name: str, repo_branch: str, repo_hash: str, repo_diff: Optional[str]):
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.repo_branch = repo_branch
        self.repo_hash = repo_hash
        self.repo_diff = repo_diff

    def __str__(self) -> str:
        return f'RepoData(repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'repo_branch="{self.repo_branch}", ' \
               f'repo_hash="{self.repo_hash}", ' \
               f'repo_diff_length={len(self.repo_diff) if self.repo_diff else None})'


class LocalRepoData(RepoData):
    def __init__(self, repo_user_name: str, repo_name: str, repo_branch: str, repo_hash: str, repo_diff: Optional[str],
                 protocol: RepoProtocol, identity_file: Optional[str],
                 oauth_token: Optional[str]):
        super().__init__(repo_user_name, repo_name, repo_branch, repo_hash, repo_diff)
        self.protocol = protocol
        self.identity_file = identity_file
        self.oauth_token = oauth_token

    def __str__(self) -> str:
        return f'LocalRepoData(repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'repo_branch="{self.repo_branch}", ' \
               f'repo_hash="{self.repo_hash}", ' \
               f'repo_diff_length={len(self.repo_diff) if self.repo_diff else None}, ' \
               f'protocol=RepoProtocol.{self.protocol.name}, ' \
               f'identity_file={_quoted(self.identity_file)}, ' \
               f'oauth_token={_quoted_masked(self.oauth_token)})'

    def ls_remote(self) -> str:
        if self.protocol == RepoProtocol.HTTPS:
            return git.cmd.Git().ls_remote(f"https://"
                                           f"{(self.oauth_token + '@') if self.oauth_token else ''}github.com/"
                                           f"{self.repo_user_name}/"
                                           f"{self.repo_name}.git")
        else:
            if self.identity_file:
                git_ssh_command = f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={self.identity_file}"
                return git.cmd.Git().ls_remote(f"git@github.com:{self.repo_user_name}/{self.repo_name}.git", env=dict(
                    GIT_SSH_COMMAND=git_ssh_command
                ))
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

        repo_url_parsed = giturlparse.parse(repo_url)
        repo_oauth_token = oauth_token
        repo_identity_file = identity_file
        repo_resource = repo_url_parsed.resource
        if repo_url_parsed.protocol == "ssh":
            ssh_config_path = os.path.expanduser('~/.ssh/config')
            if os.path.exists(ssh_config_path):
                with open(ssh_config_path, "r") as f:
                    config = SSHConfig()
                    config.parse(f)
                    c = config.lookup(repo_url_parsed.resource)
                    repo_resource = c["hostname"]
                    if not identity_file:
                        i = c.get("identityfile")
                        repo_identity_file = i[0] if i else None
                    # TODO: Detect and pass private key too
        elif not oauth_token:
            gh_config_path = os.path.expanduser('~/.config/gh/hosts.yml')
            if os.path.exists(gh_config_path):
                with open(gh_config_path, "r") as f:
                    hosts_data = yaml.load(f, Loader=yaml.FullLoader)
                    if "github.com" in hosts_data:
                        repo_oauth_token = hosts_data["github.com"].get("oauth_token")
        # TODO: Doesn't support unstaged changes
        repo_diff = repo.git.diff(repo_hash)
        if repo_resource == "github.com":
            return LocalRepoData(repo_url_parsed.owner, repo_url_parsed.name, repo_branch, repo_hash, repo_diff,
                                 RepoProtocol.HTTPS if repo_url_parsed.protocol == "https" else RepoProtocol.SSH,
                                 repo_identity_file or os.path.expanduser('~/.ssh/id_rsa'), repo_oauth_token)
        else:
            sys.exit(f"{os.getcwd()} is not a GitHub repo")
    else:
        sys.exit(f"No tracked branch configured for branch {repo.active_branch.name}")
