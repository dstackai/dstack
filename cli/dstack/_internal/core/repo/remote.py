import io
import os
import subprocess
import tempfile
import time
from typing import BinaryIO, Optional

import git
import giturlparse
from pydantic import BaseModel, Field
from typing_extensions import Literal

from dstack._internal.core.repo import RepoProtocol
from dstack._internal.core.repo.base import Repo, RepoData, RepoInfo, RepoRef
from dstack._internal.utils.common import PathLike
from dstack._internal.utils.hash import get_sha256, slugify
from dstack._internal.utils.ssh import get_host_config, make_ssh_command_for_git


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
    repo_diff: Optional[str] = Field(None, exclude=True)
    repo_config_name: Optional[str] = None
    repo_config_email: Optional[str] = None

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
            repo_data.repo_config_name = repo.config_reader().get_value("user", "name")
            repo_data.repo_config_email = repo.config_reader().get_value("user", "email")
            repo_data.repo_diff = _repo_diff_verbose(repo, repo_data.repo_hash)
        elif self.repo_url is not None:
            repo_data = RemoteRepoData.from_url(self.repo_url, parse_ssh_config=True)
        elif repo_data is None:
            raise ValueError("No remote repo data provided")

        if repo_ref is None:
            repo_ref = RepoRef(repo_id=slugify(repo_data.repo_name, repo_data.path("/")))
        super().__init__(repo_ref, repo_data)


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


class _DiffCollector:
    def __init__(self, warning_time: float, delay: float = 5):
        self.warning_time = warning_time
        self.delay = delay
        self.warned = False
        self.start_time = time.monotonic()
        self.buffer = io.StringIO()

    def timeout(self):
        now = time.monotonic()
        if not self.warned and now > self.start_time + self.warning_time:
            print(
                "Provisioning is taking longer than usual, possibly because of having too many or large local "
                "files that haven’t been pushed to Git. Tip: Exclude unnecessary files from provisioning "
                "by using the `.gitignore` file."
            )
            self.warned = True
        return (
            self.delay
            if self.warned
            else min(self.delay, self.start_time + self.warning_time - now)
        )

    def write(self, v: bytes):
        self.buffer.write(v.decode())

    def get(self) -> str:
        if self.warned:
            print()
        return self.buffer.getvalue()


def _interactive_git_proc(
    proc: git.Git.AutoInterrupt, collector: _DiffCollector, ignore_status: bool = False
):
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=collector.timeout())
            if not ignore_status and proc.poll() != 0:
                raise git.GitCommandError(proc.args, proc.poll(), stderr)
            collector.write(stdout)
            return
        except subprocess.TimeoutExpired:
            continue


def _repo_diff_verbose(repo: git.Repo, repo_hash: str, warning_time: float = 5) -> str:
    collector = _DiffCollector(warning_time)
    try:
        _interactive_git_proc(repo.git.diff(repo_hash, as_process=True), collector)
        for filename in repo.untracked_files:
            _interactive_git_proc(
                repo.git.diff("/dev/null", filename, no_index=True, binary=True, as_process=True),
                collector,
                ignore_status=True,
            )
        return collector.get()
    except KeyboardInterrupt:
        print("\nAborted")
        exit(1)
