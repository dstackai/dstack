import os
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional

import git
import giturlparse
from pydantic import BaseModel
from typing_extensions import Literal

from dstack.core.repo import RepoProtocol
from dstack.core.repo.base import Repo, RepoData, RepoInfo, RepoRef
from dstack.utils.common import PathLike
from dstack.utils.hash import get_sha256, slugify
from dstack.utils.ssh import get_host_config, make_ssh_command_for_git
from dstack.utils.workflows import load_workflows


class RemoteRepoCredentials(BaseModel):
    protocol: RepoProtocol
    private_key: Optional[str]
    oauth_token: Optional[str]


class RemoteRepoInfo(RepoInfo):
    repo_type: Literal["remote"] = "remote"
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str

    @property
    def head_key(self) -> str:
        return f"{self.repo_type};{self.repo_host_name},{self.repo_port or ''},{self.repo_user_name},{self.repo_name}"


class RemoteRepoData(RepoData, RemoteRepoInfo):
    repo_type: Literal["remote"] = "remote"
    repo_branch: Optional[str] = None
    repo_hash: Optional[str] = None
    repo_diff: Optional[str] = None

    @staticmethod
    def from_url(url: str, parse_ssh_config: bool = True):
        url = giturlparse.parse(url)
        data = RemoteRepoData(
            repo_host_name=url.resource,
            repo_port=url.port,
            repo_user_name=url.owner,
            repo_name=url.name,
        )
        if parse_ssh_config and url.protocol == "ssh":
            host_config = get_host_config(data.repo_host_name)
            data.repo_host_name = host_config.get("hostname", data.repo_host_name)
            data.repo_port = host_config.get("port", data.repo_port)
        return data

    def path(self, sep: str = ".") -> str:
        return sep.join(
            [
                self.repo_host_name
                if self.repo_port is None
                else f"{self.repo_host_name}:{self.repo_port}",
                self.repo_user_name,
                self.repo_name,
            ]
        )

    def make_url(self, protocol: RepoProtocol, oauth_token: Optional[str] = None) -> str:
        if protocol == RepoProtocol.HTTPS:
            return f"https://{(oauth_token + '@') if oauth_token else ''}{self.path(sep='/')}.git"
        elif protocol == RepoProtocol.SSH:
            if self.repo_port:
                return f"ssh@{self.path(sep='/')}.git"
            else:
                return f"git@{self.repo_host_name}:{self.repo_user_name}/{self.repo_name}.git"

    def write_code_file(self, fp: BinaryIO) -> str:
        if self.repo_diff is not None:
            fp.write(self.repo_diff.encode())
        return f"code/remote/{get_sha256(fp)}.patch"


class RemoteRepo(Repo):
    """Represents both local git repository with configured remote and just remote repository"""

    repo_data: RemoteRepoData

    def __init__(
        self,
        *,
        repo_ref: Optional[RepoRef] = None,
        local_repo_dir: Optional[PathLike] = None,
        repo_url: Optional[str] = None,
        repo_data: Optional[RemoteRepoData] = None,
    ):
        """
        >>> RemoteRepo(local_repo_dir=os.getcwd())
        >>> RemoteRepo(repo_ref=RepoRef(repo_id="playground"), repo_url="https://github.com/dstackai/dstack-playground.git")
        """

        self.local_repo_dir = local_repo_dir
        self.repo_url = repo_url

        if self.local_repo_dir is not None:
            repo = git.Repo(self.local_repo_dir)
            tracking_branch = repo.active_branch.tracking_branch()
            if tracking_branch is None:
                raise ValueError("No remote branch is configured")
            self.repo_url = repo.remote(tracking_branch.remote_name).url
            repo_data = RemoteRepoData.from_url(self.repo_url, parse_ssh_config=True)
            repo_data.repo_branch = tracking_branch.remote_head
            repo_data.repo_hash = tracking_branch.commit.hexsha
            repo_data.repo_diff = repo.git.diff(repo_data.repo_hash)
            diffs = [repo_data.repo_diff]
            for filename in repo.untracked_files:
                diffs.append(_add_patch(local_repo_dir, filename))
            repo_data.repo_diff = "\n".join([d for d in diffs if d])
        elif self.repo_url is not None:
            repo_data = RemoteRepoData.from_url(self.repo_url, parse_ssh_config=True)
        elif repo_data is None:
            raise ValueError("No remote repo data provided")

        if repo_ref is None:
            repo_ref = RepoRef(repo_id=slugify(repo_data.repo_name, repo_data.path("/")))
        super().__init__(repo_ref, repo_data)

    def get_workflows(
        self, credentials: Optional[RemoteRepoCredentials] = None
    ) -> Dict[str, Dict[str, Any]]:
        if self.local_repo_dir is not None:
            local_repo_dir = Path(self.local_repo_dir)
        elif credentials is None:
            raise RuntimeError("No credentials for remote only repo")
        else:
            temp_dir = tempfile.TemporaryDirectory()  # will be removed by garbage collector
            local_repo_dir = Path(temp_dir.name)
            _clone_remote_repo(local_repo_dir, self.repo_data, credentials, depth=1)
        return load_workflows(local_repo_dir / ".dstack")


def _clone_remote_repo(
    dst: PathLike, repo_data: RemoteRepoData, repo_credentials: RemoteRepoCredentials, **kwargs
):
    env = kwargs.pop("env", {})
    if repo_credentials.protocol == RepoProtocol.HTTPS:
        env["GIT_TERMINAL_PROMPT"] = "0"
    elif repo_credentials.protocol == RepoProtocol.SSH:
        tmp_identity_file = tempfile.NamedTemporaryFile(
            "w+b"
        )  # will be removed by garbage collector
        tmp_identity_file.write(repo_credentials.private_key.encode())
        tmp_identity_file.seek(0)
        env["GIT_SSH_COMMAND"] = make_ssh_command_for_git(tmp_identity_file.name)
    git.Repo.clone_from(
        url=repo_data.make_url(repo_credentials.protocol, repo_credentials.oauth_token),
        to_path=dst,
        env=env,
        **kwargs,
    )
    # todo checkout branch/hash


def _add_patch(repo_dir: PathLike, filename: str) -> str:
    return git.cmd.Git(repo_dir).diff(
        "/dev/null", filename, no_index=True, binary=True, with_exceptions=False
    )
