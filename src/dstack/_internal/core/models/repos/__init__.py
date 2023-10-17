from typing import Optional, Union

from pydantic import BaseModel, Field

from dstack._internal.core.models.repos.local import LocalRepo, LocalRepoInfo, LocalRunRepoData
from dstack._internal.core.models.repos.remote import (
    RemoteRepo,
    RemoteRepoCreds,
    RemoteRepoInfo,
    RemoteRunRepoData,
)
from dstack._internal.core.models.repos.virtual import VirtualRepoInfo, VirtualRunRepoData

AnyRunRepoData = Union[RemoteRunRepoData, LocalRunRepoData, VirtualRunRepoData]

AnyRepoInfo = Union[RemoteRepoInfo, LocalRepoInfo, VirtualRepoInfo]


class RepoHead(BaseModel):
    repo_id: str
    repo_info: AnyRepoInfo = Field(..., discriminator="repo_type")


class RepoHeadWithCreds(RepoHead):
    repo_creds: Optional[RemoteRepoCreds]


AnyRepoHead = Union[RepoHeadWithCreds, RepoHead]
