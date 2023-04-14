import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal, Optional, Union

import git
import giturlparse
import yaml
from paramiko.config import SSHConfig
from pydantic import BaseModel, Field, validator

from dstack.utils.common import PathLike

ssh_config_path = os.path.expanduser("~/.ssh/config")
gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")


class RepoProtocol(Enum):
    SSH = "ssh"
    HTTPS = "https"


class RepoCredentials(BaseModel):
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
    repo_protocol: Optional[str] = None

    @staticmethod
    def from_url(url: str, parse_ssh_config: bool = True):
        url = giturlparse.parse(url)
        data = RemoteRepoData(
            repo_host_name=url.resource,
            repo_port=url.port,
            repo_user_name=url.owner,
            repo_name=url.name,
            repo_protocol=url.protocol,
        )
        if parse_ssh_config and url.protocol == "ssh":
            if os.path.exists(ssh_config_path):
                config = SSHConfig()
                with open(ssh_config_path, "r") as f:
                    config.parse(f)
                host_config = config.lookup(data.repo_host_name)
                data.repo_host_name = host_config["hostname"]
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
    def get_workflows(self) -> list:
        pass

    @abstractmethod
    def get_repo_credentials(self) -> Optional[RepoCredentials]:
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
        identity_file: Optional[PathLike] = None,
        oauth_token: Optional[str] = None,
    ):
        """
        >>> RemoteRepo(local_repo_dir=os.getcwd())
        >>> RemoteRepo(repo_ref=RepoRef(repo_id="playground", repo_user_id="bob"), repo_url="https://github.com/dstackai/dstack-playground.git")
        """

        self.local_repo_dir = local_repo_dir
        self.repo_url = repo_url
        self.identity_file = identity_file
        self.oauth_token = oauth_token

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

    def get_workflows(self) -> list:
        raise NotImplementedError()

    def get_repo_credentials(self) -> Optional[RepoCredentials]:
        private_key = None
        if self.repo_data.repo_protocol == "ssh":
            if self.identity_file is None:
                if os.path.exists(ssh_config_path):
                    with open(ssh_config_path, "r") as f:
                        config = SSHConfig()
                        with open(ssh_config_path, "r") as f:
                            config.parse(f)
                        identities = config.lookup(self.repo_data.repo_host_name)["identityfile"]
                        if identities:
                            self.identity_file = os.path.expanduser(identities[0])
                        # TODO: Detect and pass private key too ?
                if self.identity_file is None:
                    self.identity_file = os.path.expanduser("~/.ssh/id_rsa")
            self.ls_remote()
            if os.path.exists(self.identity_file):
                with open(self.identity_file, "f") as f:
                    private_key = f.read()
        elif self.repo_data.repo_protocol == "https":
            if self.oauth_token is None:
                if os.path.exists(gh_config_path):
                    with open(gh_config_path, "r") as f:
                        gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
                    self.oauth_token = gh_hosts.get(self.repo_data.repo_host_name, {}).get(
                        "oauth_token"
                    )
            self.ls_remote()
        return RepoCredentials(
            protocol=RepoProtocol[self.repo_data.repo_protocol.upper()],
            private_key=private_key,
            oauth_token=self.oauth_token,
        )

    def get_repo_diff(self) -> Optional[str]:
        return self.repo_data.repo_diff

    def ls_remote(self) -> str:
        if self.repo_data.repo_protocol == "https":
            return git.cmd.Git().ls_remote(
                f"https://"
                f"{(self.oauth_token + '@') if self.oauth_token else ''}"
                f"{self.repo_data.path(sep='/')}.git"
            )
        else:
            git_ssh_command = (
                f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={self.identity_file}"
            )
            if self.repo_data.repo_port:
                url = f"ssh@{self.repo_data.path(sep='/')}.git"
            else:
                url = f"git@{self.repo_data.repo_host_name}:{self.repo_data.repo_user_name}/{self.repo_data.repo_name}.git"
            return git.cmd.Git().ls_remote(url, env=dict(GIT_SSH_COMMAND=git_ssh_command))


class RepoSpec(BaseModel):
    """Serializable Repo representation"""

    repo_ref: RepoRef
    repo_data: Union[RepoData, RemoteRepoData] = Field(..., discriminator="repo_type")

    @property
    def repo(self) -> Repo:
        """Constructs Repo implementation from `repo_data`"""
        if isinstance(self.repo_data, RemoteRepoData):
            return RemoteRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)
