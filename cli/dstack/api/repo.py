import os
import sys
import giturlparse
from typing import Optional
import yaml
from git import Repo as GitRepo
from paramiko.config import SSHConfig

from dstack.core.repo import LocalRepoData, RepoProtocol


def load_repo_data(
    oauth_token: Optional[str] = None, identity_file: Optional[str] = None
) -> LocalRepoData:
    # TODO: Allow to override the current working directory, e.g. via --dir
    cwd = os.getcwd()
    repo = GitRepo(cwd)
    tracking_branch = repo.active_branch.tracking_branch()
    if tracking_branch:
        repo_branch = tracking_branch.remote_head
        remote_name = tracking_branch.remote_name
        repo_hash = tracking_branch.commit.hexsha
        repo_url = repo.remote(remote_name).url

        local_repo_user_name = repo.config_reader().get_value("user", "name", "") or None
        local_repo_user_email = repo.config_reader().get_value("user", "email", "") or None

        repo_url_parsed = giturlparse.parse(repo_url)
        repo_oauth_token = oauth_token
        repo_identity_file = identity_file
        repo_host_name = repo_url_parsed.resource
        repo_port = repo_url_parsed.port
        if repo_url_parsed.protocol == "ssh":
            ssh_config_path = os.path.expanduser("~/.ssh/config")
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
            gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")
            if os.path.exists(gh_config_path):
                with open(gh_config_path, "r") as f:
                    hosts_data = yaml.load(f, Loader=yaml.FullLoader)
                    if repo_host_name in hosts_data:
                        repo_oauth_token = hosts_data[repo_host_name].get("oauth_token")
        # TODO: Doesn't support unstaged changes
        repo_diff = repo.git.diff(repo_hash)
        return LocalRepoData(
            repo_host_name,
            repo_port,
            repo_url_parsed.owner,
            repo_url_parsed.name,
            repo_branch,
            repo_hash,
            repo_diff,
            RepoProtocol.HTTPS if repo_url_parsed.protocol == "https" else RepoProtocol.SSH,
            repo_identity_file or os.path.expanduser("~/.ssh/id_rsa"),
            repo_oauth_token,
            local_repo_user_name,
            local_repo_user_email,
        )
    else:
        sys.exit(f"No tracked branch configured for branch {repo.active_branch.name}")
