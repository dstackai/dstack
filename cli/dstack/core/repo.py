import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Union

import git
import giturlparse
from pydantic import BaseModel, Field, validator
from typing_extensions import Literal

from dstack.utils.common import PathLike
from dstack.utils.ssh import get_host_config


class RepoProtocol(Enum):
    SSH = "ssh"
    HTTPS = "https"


class RemoteRepoCredentials(BaseModel):
    protocol: RepoProtocol
    private_key: Optional[str]
    oauth_token: Optional[str]


class RepoRef(BaseModel):
    repo_id: str
    repo_user_id: str

    @validator("repo_id", "repo_user_id")
    def validate_id(cls, value):
        for c in "/;":
            if c in value:
                raise ValueError(f"id can't contain `{c}`")
        return value


class RepoHead(RepoRef):
    last_run_at: Optional[int] = None
    tags_count: int = 0


class RepoData(BaseModel):
    repo_type: Literal["none"] = "none"


class RemoteRepoData(RepoData):
    repo_type: Literal["remote"] = "remote"
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str
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


class Repo(ABC):
    def __init__(self, repo_ref: RepoRef, repo_data: RepoData):
        self.repo_ref = repo_ref
        self.repo_data = repo_data

    @property
    def repo_id(self) -> str:
        return self.repo_ref.repo_id

    @property
    def repo_user_id(self) -> str:
        return self.repo_ref.repo_user_id

    @property
    def repo_spec(self) -> "RepoSpec":
        return RepoSpec(repo_ref=self.repo_ref, repo_data=self.repo_data)

    @abstractmethod
    def get_workflows(self, credentials: Optional[RemoteRepoCredentials] = None) -> list:
        pass

    @abstractmethod
    def get_repo_diff(self) -> Optional[str]:
        pass


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
        >>> RemoteRepo(repo_ref=RepoRef(repo_id="playground", repo_user_id="bob"), repo_url="https://github.com/dstackai/dstack-playground.git")
        """

        self.local_repo_dir = local_repo_dir
        self.repo_url = repo_url

        repo_user_id = "default"
        if self.local_repo_dir is not None:
            repo = git.Repo(self.local_repo_dir)
            tracking_branch = repo.active_branch.tracking_branch()
            if tracking_branch is None:
                raise ValueError("No remote branch is configured")
            self.repo_url = repo.remote(tracking_branch.remote_name).url
            repo_data = RemoteRepoData.from_url(self.repo_url, parse_ssh_config=True)
            repo_data.repo_branch = tracking_branch.remote_head
            repo_data.repo_hash = tracking_branch.commit.hexsha
            repo_data.repo_diff = repo.git.diff(
                repo_data.repo_hash
            )  # TODO: Doesn't support unstaged changes
            repo_user_id = repo.config_reader().get_value("user", "email", "") or repo_user_id
        elif self.repo_url is not None:
            repo_data = RemoteRepoData.from_url(self.repo_url, parse_ssh_config=True)
        elif repo_data is None:
            raise ValueError("No remote repo data provided")

        if repo_ref is None:
            repo_ref = RepoRef(repo_id=repo_data.path(), repo_user_id=repo_user_id)
        super().__init__(repo_ref, repo_data)

    def get_workflows(self, credentials: Optional[RemoteRepoCredentials] = None) -> list:
        raise NotImplementedError()

    def get_repo_diff(self) -> Optional[str]:
        return self.repo_data.repo_diff


class RepoSpec(BaseModel):
    """Serializable Repo representation"""

    repo_ref: RepoRef
    repo_data: Union[RepoData, RemoteRepoData] = Field(..., discriminator="repo_type")

    @property
    def repo(self) -> Repo:
        """Constructs Repo implementation from `repo_data`"""
        if isinstance(self.repo_data, RemoteRepoData):
            return RemoteRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)
