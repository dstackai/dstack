from enum import Enum
from typing import Optional, Union

import git
from pydantic import BaseModel, validator


class RepoProtocol(Enum):
    SSH = "ssh"
    HTTPS = "https"


class RepoAddress(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str

    def path(self, delimiter: str = "/"):
        return (
            f"{self.repo_host_name}"
            f"{(':' + str(self.repo_port)) if self.repo_port else ''}{delimiter}"
            f"{self.repo_user_name}{delimiter}{self.repo_name}"
        )


class RepoCredentials(BaseModel):
    protocol: RepoProtocol
    private_key: Optional[str]
    oauth_token: Optional[str]


class RepoData(RepoAddress):
    repo_branch: Optional[str]
    repo_hash: Optional[str]
    repo_diff: Optional[str]


class LocalRepoData(RepoData):
    protocol: RepoProtocol
    identity_file: Optional[str]
    oauth_token: Optional[str]
    local_repo_user_name: Optional[str]
    local_repo_user_email: Optional[str]

    def ls_remote(self) -> str:
        if self.protocol == RepoProtocol.HTTPS:
            return git.cmd.Git().ls_remote(
                f"https://"
                f"{(self.oauth_token + '@') if self.oauth_token else ''}"
                f"{self.path()}.git"
            )
        else:
            if self.identity_file:
                git_ssh_command = (
                    f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={self.identity_file}"
                )
                if self.repo_port:
                    url = f"ssh@{self.path()}.git"
                else:
                    url = f"git@{self.repo_host_name}:{self.repo_user_name}/{self.repo_name}.git"
                return git.cmd.Git().ls_remote(url, env=dict(GIT_SSH_COMMAND=git_ssh_command))
            else:
                raise Exception("No identity file is specified")

    def repo_credentials(self) -> RepoCredentials:
        if self.protocol == RepoProtocol.HTTPS:
            return RepoCredentials(
                protocol=self.protocol, private_key=None, oauth_token=self.oauth_token
            )
        elif self.identity_file:
            with open(self.identity_file, "r") as f:
                return RepoCredentials(
                    protocol=self.protocol, private_key=f.read(), oauth_token=None
                )
        else:
            raise Exception("No identity file is specified")


class RepoRef(BaseModel):
    repo_id: str
    repo_user_id: str
    data: Optional[Union[RepoData, LocalRepoData]] = None

    @validator("repo_id", "repo_user_id")
    def validate_id(cls, value):
        for c in "/;":
            if c in value:
                raise ValueError(f"id can't contain `{c}`")
        return value


class RepoHead(RepoRef):
    last_run_at: Optional[int] = None
    tags_count: int = 0
