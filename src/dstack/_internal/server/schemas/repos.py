from typing import List, Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos import AnyRepoInfo
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.server.schemas.common import RepoRequest


class GetRepoRequest(RepoRequest):
    include_creds: bool


class SaveRepoCredsRequest(RepoRequest):
    repo_info: AnyRepoInfo
    repo_creds: Optional[RemoteRepoCreds]


class DeleteReposRequest(CoreModel):
    repos_ids: List[str]
