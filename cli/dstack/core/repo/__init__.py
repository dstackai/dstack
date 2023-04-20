from dstack.core.repo.base import Repo, RepoData, RepoProtocol, RepoRef
from dstack.core.repo.local import LocalRepoData
from dstack.core.repo.remote import (
    RemoteRepo,
    RemoteRepoCredentials,
    RemoteRepoData,
    RemoteRepoHead,
    RemoteRepoInfo,
)
from dstack.core.repo.spec import RepoSpec

RepoHead = RemoteRepoHead
