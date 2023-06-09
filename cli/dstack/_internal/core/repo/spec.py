from typing import Union

from pydantic import BaseModel, Field

from dstack._internal.core.repo.base import Repo, RepoData, RepoRef
from dstack._internal.core.repo.local import LocalRepo, LocalRepoData
from dstack._internal.core.repo.remote import RemoteRepo, RemoteRepoData


class RepoSpec(BaseModel):
    """Serializable Repo representation"""

    repo_ref: RepoRef
    repo_data: Union[RepoData, LocalRepoData, RemoteRepoData] = Field(
        ..., discriminator="repo_type"
    )

    @property
    def repo(self) -> Repo:
        """Constructs Repo implementation from `repo_data`"""
        if isinstance(self.repo_data, RemoteRepoData):
            return RemoteRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)
        if isinstance(self.repo_data, LocalRepoData):
            return LocalRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)

    @classmethod
    def from_repo(cls, repo: Repo) -> "RepoSpec":
        return RepoSpec(repo_ref=repo.repo_ref, repo_data=repo.repo_data)
