from typing import Annotated, List, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos import AnyRepoInfo
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.server.schemas.common import RepoRequest


class GetRepoRequest(RepoRequest):
    include_creds: bool


class SaveRepoCredsRequest(RepoRequest):
    repo_info: Annotated[AnyRepoInfo, Field(discriminator="repo_type")]
    repo_creds: Annotated[
        Optional[RemoteRepoCreds],
        Field(description="The repo creds for accessing private remote repo"),
    ] = None


class DeleteReposRequest(CoreModel):
    repos_ids: List[str]
