from typing import Optional, Union

import giturlparse
import requests

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo
from dstack._internal.core.services.repos import (
    InvalidRepoCredentialsError,
    get_local_repo_credentials,
)
from dstack._internal.utils.path import PathLike
from dstack.api.server import APIClient


class RepoCollection:
    """
    Operations with repos
    """

    def __init__(self, api_client: APIClient, project: str, repo: Union[RemoteRepo, LocalRepo]):
        self._api_client = api_client
        self._project = project
        self._repo = repo

    def init(
        self,
        git_identity_file: Optional[PathLike] = None,
        oauth_token: Optional[str] = None,
    ):
        """
        Upload credentials and initializes the remote repo in the project

        Args:
            git_identity_file: SSH private key to access the remote repo
            oauth_token: GitHub OAuth token to access the remote repo
        """
        creds = None
        if isinstance(self._repo, RemoteRepo):
            try:
                creds = get_local_repo_credentials(
                    repo_data=self._repo.run_repo_data,
                    identity_file=git_identity_file,
                    oauth_token=oauth_token,
                    original_hostname=giturlparse.parse(self._repo.repo_url).resource,
                )
            except InvalidRepoCredentialsError as e:
                raise ConfigurationError(*e.args)
        self._api_client.repos.init(
            self._project, self._repo.repo_id, self._repo.run_repo_data, creds
        )

    def is_initialized(self) -> bool:
        """
        Checks if the remote repo is initialized in the project

        Returns:
            repo is initialized
        """
        try:
            self._api_client.repos.get(self._project, self._repo.repo_id, include_creds=False)
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return False
            raise
