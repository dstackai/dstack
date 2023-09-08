from typing import Union

from dstack._internal.core.models.repos.base import Repo, RepoData, RepoProtocol, RepoRef
from dstack._internal.core.models.repos.head import Repo
from dstack._internal.core.models.repos.local import LocalRepo, LocalRepoData, LocalRepoInfo
from dstack._internal.core.models.repos.remote import (
    RemoteRepo,
    RemoteRepoCredentials,
    RemoteRepoData,
    RemoteRepoInfo,
)
from dstack._internal.core.models.repos.spec import RepoSpec

AnyRepoData = Union[RemoteRepoData, LocalRepoData]
