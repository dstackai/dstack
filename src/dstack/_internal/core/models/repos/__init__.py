from typing import Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos.local import (  # noqa: F401
    LocalRepo,
    LocalRepoInfo,
    LocalRunRepoData,
)
from dstack._internal.core.models.repos.remote import (  # noqa: F401
    RemoteRepo,
    RemoteRepoCreds,
    RemoteRepoInfo,
    RemoteRunRepoData,
)
from dstack._internal.core.models.repos.virtual import VirtualRepoInfo, VirtualRunRepoData

AnyRunRepoData = Union[RemoteRunRepoData, LocalRunRepoData, VirtualRunRepoData]

AnyRepoInfo = Union[RemoteRepoInfo, LocalRepoInfo, VirtualRepoInfo]


class RepoHead(CoreModel):
    repo_id: str
    repo_info: AnyRepoInfo = Field(..., discriminator="repo_type")


class RepoHeadWithCreds(RepoHead):
    repo_creds: Optional[RemoteRepoCreds]


AnyRepoHead = Union[RepoHeadWithCreds, RepoHead]
