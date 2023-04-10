from enum import Enum
from typing import Any, Optional, Union

import git
from pydantic import BaseModel

from dstack.utils.common import _quoted, _quoted_masked


class RepoAddress(BaseModel):
    repo_host_name: str
    repo_port: Union[int, None]
    repo_user_name: str
    repo_name: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    def __str__(self) -> str:
        return (
            f'RepoAddress(repo_host_name="{self.repo_host_name}", '
            f'repo_port={_quoted(self.repo_port)}", '
            f'repo_user_name="{self.repo_user_name}", '
            f'repo_name="{self.repo_name}")'
        )

    def path(self, delimiter: str = "/"):
        return (
            f"{self.repo_host_name}"
            f"{(':' + str(self.repo_port)) if self.repo_port else ''}{delimiter}"
            f"{self.repo_user_name}{delimiter}{self.repo_name}"
        )


class RepoHead(RepoAddress):
    last_run_at: Union[int, None]
    tags_count: int

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    def __str__(self) -> str:
        return (
            f'RepoHead(repo_host_name="{self.repo_host_name}", '
            f'repo_port={_quoted(self.repo_port)}", '
            f'repo_user_name="{self.repo_user_name}", '
            f'repo_name="{self.repo_name}", '
            f'last_run_at="{self.last_run_at}", '
            f'tags_count="{self.tags_count}")'
        )


class RepoProtocol(Enum):
    SSH = "ssh"
    HTTPS = "https"


class RepoCredentials(BaseModel):
    protocol: RepoProtocol
    private_key: Union[str, None]
    oauth_token: Union[str, None]

    def __str__(self) -> str:
        return (
            f"RepoCredentials(protocol=RepoProtocol.{self.protocol.name}, "
            f"private_key_length={len(self.private_key) if self.private_key else None}, "
            f"oauth_token={_quoted_masked(self.oauth_token)})"
        )


class RepoData(RepoAddress):
    repo_branch: Optional[str]
    repo_hash: Optional[str]
    repo_diff: Union[str, None]

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    def __str__(self) -> str:
        return (
            f'RepoData(repo_host_name="{self.repo_host_name}", '
            f'repo_port={_quoted(self.repo_port)}", '
            f'repo_user_name="{self.repo_user_name}", '
            f'repo_name="{self.repo_name}", '
            f'repo_branch="{_quoted(self.repo_branch)}", '
            f'repo_hash="{_quoted(self.repo_hash)}", '
            f"repo_diff_length={len(self.repo_diff) if self.repo_diff else None})"
        )


class LocalRepoData(RepoData):
    protocol: RepoProtocol
    identity_file: Union[str, None]
    oauth_token: Union[str, None]
    local_repo_user_name: Union[str, None]
    local_repo_user_email: Union[str, None]

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    def __str__(self) -> str:
        return (
            f'LocalRepoData(repo_host_name="{self.repo_host_name}", '
            f'repo_port={_quoted(self.repo_port)}", '
            f'repo_user_name="{self.repo_user_name}", '
            f'repo_name="{self.repo_name}", '
            f'repo_branch="{_quoted(self.repo_branch)}", '
            f'repo_hash="{_quoted(self.repo_hash)}", '
            f"repo_diff_length={len(self.repo_diff) if self.repo_diff else None}, "
            f"protocol=RepoProtocol.{self.protocol.name}, "
            f"identity_file={_quoted(self.identity_file)}, "
            f"oauth_token={_quoted_masked(self.oauth_token)},"
            f'local_repo_user_name="{_quoted(self.local_repo_user_name)}, '
            f"local_repo_user_email={_quoted(self.local_repo_user_email)})"
        )

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
