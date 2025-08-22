import io
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Annotated, Any, BinaryIO, Callable, Dict, Optional

import git
import pydantic
from pydantic import Field
from typing_extensions import Literal

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos.base import BaseRepoInfo, Repo
from dstack._internal.utils.hash import get_sha256, slugify
from dstack._internal.utils.path import PathLike
from dstack._internal.utils.ssh import get_host_config

SCP_LOCATION_REGEX = re.compile(r"(?P<user>[^/]+)@(?P<host>[^/]+?):(?P<path>.+)", re.IGNORECASE)


class RepoError(DstackError):
    pass


class RemoteRepoCreds(CoreModel):
    clone_url: str
    private_key: Optional[str]
    oauth_token: Optional[str]

    # TODO: remove in 0.20. Left for compatibility with CLI <=0.18.44
    protocol: Annotated[Optional[str], Field(exclude=True)] = None

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]) -> None:
            del schema["properties"]["protocol"]


class RemoteRepoInfo(BaseRepoInfo):
    repo_type: Literal["remote"] = "remote"
    repo_name: str

    # TODO: remove in 0.20. Left for compatibility with CLI <=0.18.44
    repo_host_name: Annotated[Optional[str], Field(exclude=True)] = None
    repo_port: Annotated[Optional[int], Field(exclude=True)] = None
    repo_user_name: Annotated[Optional[str], Field(exclude=True)] = None

    class Config(BaseRepoInfo.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]) -> None:
            del schema["properties"]["repo_host_name"]
            del schema["properties"]["repo_port"]
            del schema["properties"]["repo_user_name"]


class RemoteRunRepoData(RemoteRepoInfo):
    repo_branch: Optional[str] = None
    repo_hash: Optional[str] = None
    repo_diff: Optional[str] = Field(None, exclude=True)
    repo_config_name: Optional[str] = None
    repo_config_email: Optional[str] = None

    @staticmethod
    def from_url(url: str):
        return RemoteRunRepoData(repo_name=GitRepoURL.parse(url).get_repo_name())


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
    run = client.runs.apply_configuration(
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
            repo_dir: The path to a local folder.

        Returns:
            A remote repo instance.
        """
        return RemoteRepo(local_repo_dir=repo_dir)

    @staticmethod
    def from_url(
        repo_url: str, repo_branch: Optional[str] = None, repo_hash: Optional[str] = None
    ) -> "RemoteRepo":
        """
        Creates an instance of a remote repo from a URL.

        Args:
            repo_url: The URL of a remote Git repo.
            repo_branch: The name of the remote branch. Must be specified if `hash` is not specified.
            repo_hash: The hash of the revision. Must be specified if `branch` is not specified.

        Returns:
            A remote repo instance.
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
            repo_data = RemoteRunRepoData.from_url(self.repo_url)
            repo_data.repo_branch = tracking_branch.remote_head
            repo_data.repo_hash = tracking_branch.commit.hexsha
            repo_data.repo_config_name = repo.config_reader().get_value("user", "name", "") or None
            repo_data.repo_config_email = (
                repo.config_reader().get_value("user", "email", "") or None
            )
            repo_data.repo_diff = _repo_diff_verbose(repo, repo_data.repo_hash)
        elif self.repo_url is not None:
            repo_data = RemoteRunRepoData.from_url(self.repo_url)
            if repo_branch is not None:
                repo_data.repo_branch = repo_branch
            if repo_hash is not None:
                repo_data.repo_hash = repo_hash
        elif repo_data is None:
            raise RepoError("No remote repo data provided")

        if repo_id is None:
            repo_id = slugify(
                repo_data.repo_name,
                GitRepoURL.parse(
                    self.repo_url, get_ssh_config=get_host_config
                ).get_unique_location(),
            )
        self.repo_id = repo_id
        self.run_repo_data = repo_data

    def write_code_file(self, fp: BinaryIO) -> str:
        if self.run_repo_data.repo_diff is not None:
            fp.write(self.run_repo_data.repo_diff.encode())
        return get_sha256(fp)

    def get_repo_info(self) -> RemoteRepoInfo:
        return RemoteRepoInfo(repo_name=self.run_repo_data.repo_name)


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


@dataclass
class GitRepoURL:
    """
    Class for best-effort repo URLs parsing and conversion to https:// or ssh:// form.
    """

    ssh_user: Optional[str]
    host: str
    https_port: Optional[str]
    ssh_port: Optional[str]
    path: str

    original_host: str  # before SSH config lookup

    @staticmethod
    def parse(
        value: str,
        get_ssh_config: Callable[[str], Dict[str, str]] = lambda host: {},
    ) -> "GitRepoURL":
        try:
            url = pydantic.parse_obj_as(pydantic.AnyUrl, value)
        except pydantic.ValidationError:
            url = scp_location_to_ssh_url(value)

        if url is None:
            raise RepoError(f"Could not parse git URL {value}")

        ssh_config = get_ssh_config(url.host)

        if url.scheme.lower() == "https":
            return GitRepoURL(
                ssh_user=ssh_config.get("user"),
                host=url.host.lower(),
                https_port=url.port,
                ssh_port=ssh_config.get("port"),
                path=url.path or "/",
                original_host=url.host.lower(),
            )

        if url.scheme.lower() == "ssh":
            return GitRepoURL(
                ssh_user=url.user or ssh_config.get("user"),
                host=ssh_config.get("hostname", "").lower() or url.host.lower(),
                https_port=None,
                ssh_port=url.port or ssh_config.get("port"),
                path=url.path or "/",
                original_host=url.host.lower(),
            )

        raise RepoError(f"Unsupported URL scheme {url.scheme}")

    def as_https(self, oauth_token: Optional[str] = None) -> str:
        optional_creds = f"anything:{oauth_token}@" if oauth_token else ""
        optional_port = f":{self.https_port}" if self.https_port else ""
        return f"https://{optional_creds}{self.host}{optional_port}{self.path}"

    def as_ssh(self) -> str:
        user = self.ssh_user or "git"
        optional_port = f":{self.ssh_port}" if self.ssh_port else ""
        return f"ssh://{user}@{self.host}{optional_port}{self.path}"

    def get_clean_path(self) -> str:
        return self.path.rstrip("/").removesuffix(".git")

    def get_repo_name(self) -> str:
        return self.get_clean_path().rsplit("/")[-1] or "unknown"

    def get_unique_location(self) -> str:
        return self.host + self.get_clean_path()


def scp_location_to_ssh_url(scp_location: str) -> Optional[pydantic.AnyHttpUrl]:
    """
    Converts scp-format location to SSH URL.
    E.g. git@github.com:dstackai/dstack.git" -> ssh://git@github.com/dstackai/dstack.git
    """

    match = re.match(SCP_LOCATION_REGEX, scp_location)
    if match is None:
        return None
    user, host, path = match.group("user"), match.group("host"), match.group("path")
    try:
        return pydantic.parse_obj_as(pydantic.AnyUrl, f"ssh://{user}@{host}/{path}")
    except pydantic.ValidationError:
        return None


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
