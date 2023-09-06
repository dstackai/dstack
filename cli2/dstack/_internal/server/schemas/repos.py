from typing import List

from dstack._internal.core.repo.remote import RemoteRepoCredentials
from dstack._internal.server.schemas.common import RepoRequest


class GetRepoRequest(RepoRequest):
    pass


class SaveRepoCredentialsRequest(RepoRequest):
    credentials: RemoteRepoCredentials


class GetRepoCredentialsRequest(RepoRequest):
    pass


class DeleteReposRequest(RepoRequest):
    repos_ids: List[str]
