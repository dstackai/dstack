from typing import Optional, Union

from pydantic import BaseModel, Field

from dstack._internal.core.repo.base import RepoInfo
from dstack._internal.core.repo.local import LocalRepoInfo
from dstack._internal.core.repo.remote import RemoteRepoInfo


class Repo(BaseModel):
    repo_id: str
    repo_info: Union[RepoInfo, RemoteRepoInfo, LocalRepoInfo] = Field(
        ..., discriminator="repo_type"
    )

    @property
    def repo_type(self) -> str:
        return self.repo_info.repo_type
