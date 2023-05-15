from typing import Optional, Union

from pydantic import BaseModel, Field

from dstack.core.repo.base import RepoInfo
from dstack.core.repo.local import LocalRepoInfo
from dstack.core.repo.remote import RemoteRepoInfo


class RepoHead(BaseModel):
    repo_id: str
    last_run_at: Optional[int] = None
    tags_count: int = 0
    repo_info: Union[RepoInfo, RemoteRepoInfo, LocalRepoInfo] = Field(
        ..., discriminator="repo_type"
    )

    @property
    def repo_type(self) -> str:
        return self.repo_info.repo_type
