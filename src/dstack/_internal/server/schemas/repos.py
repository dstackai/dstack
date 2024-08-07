from typing import List, Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos import AnyRepoInfo
from dstack._internal.core.models.repos.base import RepoProtocol
from dstack._internal.core.models.repos.remote import RemoteRepoCreds, RemoteRepoInfo
from dstack._internal.server.schemas.common import RepoRequest


# TODO: in 0.19, either remove this model or make clone_url required
class RemoteRepoCredsDto(CoreModel):
    protocol: RepoProtocol
    clone_url: Optional[str]
    private_key: Optional[str]
    oauth_token: Optional[str]

    @staticmethod
    def from_remote_repo_creds(creds: RemoteRepoCreds) -> "RemoteRepoCredsDto":
        return RemoteRepoCredsDto(
            protocol=creds.protocol,
            clone_url=creds.clone_url,
            private_key=creds.private_key,
            oauth_token=creds.oauth_token,
        )

    def to_remote_repo_creds(self, info: RemoteRepoInfo) -> RemoteRepoCreds:
        if (clone_url := self.clone_url) is None:
            netloc = (
                f"{info.repo_host_name}:{info.repo_port}"
                if info.repo_port
                else info.repo_host_name
            )
            if self.protocol == RepoProtocol.SSH:
                clone_url = f"ssh://git@{netloc}/{info.repo_user_name}/{info.repo_name}.git"
            else:
                clone_url = f"https://{netloc}/{info.repo_user_name}/{info.repo_name}.git"
        return RemoteRepoCreds(
            protocol=self.protocol,
            clone_url=clone_url,
            private_key=self.private_key,
            oauth_token=self.oauth_token,
        )


class GetRepoRequest(RepoRequest):
    include_creds: bool


class SaveRepoCredsRequest(RepoRequest):
    repo_info: AnyRepoInfo
    repo_creds: Optional[RemoteRepoCredsDto]


class DeleteReposRequest(CoreModel):
    repos_ids: List[str]
