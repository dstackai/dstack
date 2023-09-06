import os
from typing import Optional

from dstack._internal.cli.utils.config import get_hub_client
from dstack._internal.cli.utils.init import init_repo
from dstack.api.hub import HubClient


class RepoCollection:
    _hub_client: HubClient

    def __init__(self, hub_client: HubClient) -> None:
        super().__init__()
        self._hub_client = hub_client

    def init(
        self,
        git_identity_file: Optional[str] = None,
        oauth_token: Optional[str] = None,
        ssh_identity_file: Optional[str] = None,
    ):
        init_repo(self._hub_client, git_identity_file, oauth_token, ssh_identity_file)


class Client:
    _hub_client: HubClient
    repos: RepoCollection

    def __init__(self, hub_client: HubClient) -> None:
        super().__init__()
        self._hub_client = hub_client
        self.repos = RepoCollection(hub_client)

    @staticmethod
    def from_config(repo_dir: os.PathLike, project_name: Optional[str] = None):
        return Client(get_hub_client(project_name=project_name, repo_dir=repo_dir))
