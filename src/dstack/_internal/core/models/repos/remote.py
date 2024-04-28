import io
import subprocess
import time
from typing import BinaryIO, Optional

import git
import giturlparse
from pydantic import Field
from typing_extensions import Literal

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos.base import BaseRepoInfo, Repo, RepoProtocol
from dstack._internal.utils.hash import get_sha256, slugify
from dstack._internal.utils.path import PathLike
from dstack._internal.utils.ssh import get_host_config


class RepoError(DstackError):
    pass


class RemoteRepoCreds(CoreModel):
    protocol: RepoProtocol
    private_key: Optional[str]
    oauth_token: Optional[str]


class RemoteRepoInfo(BaseRepoInfo):
    repo_type: Literal["remote"] = "remote"
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str


class RemoteRunRepoData(RemoteRepoInfo):
    repo_branch: Optional[str] = None
    repo_hash: Optional[str] = None
    repo_diff: Optional[str] = Field(None, exclude=True)
    repo_config_name: Optional[str] = None
    repo_config_email: Optional[str] = None

    @staticmethod
    def from_url(url: str, parse_ssh_config: bool = True):
        url = giturlparse.parse(url)
        data = RemoteRunRepoData(
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


class RemoteRepo(Repo):
    """
    Creates an instance of a remote Git repo for mounting to a submitted run.

    Using a locally checked-out remote Git repo:

    ```python
    repo=RemoteRepo.from_dir(repo_dir=".")
    ```

    Using a remote Git repo by a URL:

    ```python
    repo=RemoteRepo.from_url(
        repo_url="https://github.com/dstackai/dstack-examples",
        repo_branch="main"
    )
    ```

    Initialize the repo before mounting it.

    ```python
    client.repos.init(repo)
    ```

    By default, it uses the default Git credentials configured on the machine.
    You can override these credentials via the `git_identity_file` or `oauth_token` arguments of the `init` method.

    Finally, you can pass the repo object to the run:

    ```python
    run = client.runs.submit(
        configuration=...,
        repo=repo,
    )
    ```

    """

    run_repo_data: RemoteRunRepoData

    @staticmethod
    def from_dir(repo_dir: PathLike) -> "RemoteRepo":
        """
        Creates an instance of a remote repo from a local path.

        Args:
            repo_dir: The path to a local folder

        Returns:
            A remote repo instance
        """
        return RemoteRepo(local_repo_dir=repo_dir)

    @staticmethod
    def from_url(
        repo_url: str, repo_branch: Optional[str] = None, repo_hash: Optional[str] = None
    ) -> "RemoteRepo":
        """
        Creates an instance of a remote repo from a URL.

        Args:
            repo_url: The URL of a remote Git repo
            repo_branch: The name of the remote branch. Must be specified if `hash` is not specified.
            repo_hash: The hash of the revision. Must be specified if `branch` is not specified.

        Returns:
            A remote repo instance
        """
        if repo_branch is None and repo_hash is None:
            raise ValueError("Either `repo_branch` or `repo_hash` must be specified.")
        return RemoteRepo(
            repo_url=repo_url,
            repo_branch=repo_branch,
            repo_hash=repo_hash,
        )

    def __init__(
        self,
        *,
        repo_id: Optional[str] = None,
        local_repo_dir: Optional[PathLike] = None,
        repo_url: Optional[str] = None,
        repo_data: Optional[RemoteRunRepoData] = None,
        repo_branch: Optional[str] = None,
        repo_hash: Optional[str] = None,
    ):
        self.repo_dir = local_repo_dir
        self.repo_url = repo_url

        if self.repo_dir is not None:
            repo = git.Repo(self.repo_dir)
            tracking_branch = repo.active_branch.tracking_branch()
            if tracking_branch is None:
                raise RepoError("No remote branch is configured")
            self.repo_url = repo.remote(tracking_branch.remote_name).url
            repo_data = RemoteRunRepoData.from_url(self.repo_url, parse_ssh_config=True)
            repo_data.repo_branch = tracking_branch.remote_head
            repo_data.repo_hash = tracking_branch.commit.hexsha
            repo_data.repo_config_name = repo.config_reader().get_value("user", "name", "") or None
            repo_data.repo_config_email = (
                repo.config_reader().get_value("user", "email", "") or None
            )
            repo_data.repo_diff = _repo_diff_verbose(repo, repo_data.repo_hash)
        elif self.repo_url is not None:
            repo_data = RemoteRunRepoData.from_url(self.repo_url, parse_ssh_config=True)
            if repo_branch is not None:
                repo_data.repo_branch = repo_branch
            if repo_hash is not None:
                repo_data.repo_hash = repo_hash
        elif repo_data is None:
            raise RepoError("No remote repo data provided")

        if repo_id is None:
            repo_id = slugify(repo_data.repo_name, repo_data.path("/"))
        self.repo_id = repo_id
        self.run_repo_data = repo_data

    def write_code_file(self, fp: BinaryIO) -> str:
        if self.run_repo_data.repo_diff is not None:
            fp.write(self.run_repo_data.repo_diff.encode())
        return get_sha256(fp)

    def get_repo_info(self) -> RemoteRepoInfo:
        return RemoteRepoInfo(
            repo_host_name=self.run_repo_data.repo_host_name,
            repo_port=self.run_repo_data.repo_port,
            repo_user_name=self.run_repo_data.repo_user_name,
            repo_name=self.run_repo_data.repo_name,
        )


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
                "files that haven't been pushed to Git. Tip: Exclude unnecessary files from provisioning "
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
