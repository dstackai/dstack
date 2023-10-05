from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.repos import AnyRepoInfo
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.server.schemas.common import RepoRequest


class GetRepoRequest(RepoRequest):
    include_creds: bool


class SaveRepoCredsRequest(RepoRequest):
    repo_info: AnyRepoInfo
    repo_creds: Optional[RemoteRepoCreds]


class DeleteReposRequest(BaseModel):
    repos_ids: List[str]
