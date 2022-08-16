import os
import re
import sys
from typing import Optional

import giturlparse
from git import Repo as GitRepo
from paramiko.config import SSHConfig


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


def load_repo_data() -> RepoData:
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

        if repo_url_parsed.protocol == "ssh":
            ssh_config_path = os.path.expanduser('~/.ssh/config')
            if os.path.exists(ssh_config_path):
                fp = open(ssh_config_path, 'r')
                config = SSHConfig()
                config.parse(fp)
                repo_url = repo_url.replace(repo_url_parsed.resource,
                                            config.lookup(repo_url_parsed.resource)['hostname'])
                # TODO: Detect and pass private key too
                fp.close()

        # TODO: Doesn't support unstaged changes
        repo_diff = repo.git.diff(repo_hash)
        result = re.compile("^(https://|git@)github.com/([^/]+)/([^.]+)(\\.git)?$").match(repo_url)
        if result:
            repo_user_name = result.group(2)
            repo_name = result.group(3)
            return RepoData(repo_user_name, repo_name, repo_branch, repo_hash, repo_diff)
        else:
            sys.exit(f"{os.getcwd()} is not a GitHub repo")
    else:
        sys.exit(f"No tracked branch configured for branch {repo.active_branch.name}")
