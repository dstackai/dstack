from typing import Optional

import dstack._internal.core.services.api_client as api_client_service
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike
from dstack.api._public.backends import BackendCollection
from dstack.api._public.pools import PoolCollection
from dstack.api._public.repos import RepoCollection, get_ssh_keypair
from dstack.api._public.runs import RunCollection
from dstack.api.server import APIClient

logger = get_logger(__name__)


class Client:
    """
    High-level API client for interacting with dstack server

    Attributes:
        runs: Operations with runs.
        repos: Operations with repositories.
        backends: Operations with backends.
    """

    def __init__(
        self,
        api_client: APIClient,
        project_name: str,
        ssh_identity_file: Optional[PathLike] = None,
    ):
        # """
        # Args:
        #     api_client: low-level server API client
        #     project_name: project name used for runs
        #     ssh_identity_file: SSH keypair to access instances
        # """
        self._client = api_client
        self._project = project_name
        self._repos = RepoCollection(api_client, project_name)
        self._backends = BackendCollection(api_client, project_name)
        self._runs = RunCollection(api_client, project_name, self)
        self._pool = PoolCollection(api_client, project_name)
        if ssh_identity_file:
            self.ssh_identity_file = str(ssh_identity_file)
        else:
            self.ssh_identity_file = get_ssh_keypair(None, ConfigManager().dstack_key_path)

    @staticmethod
    def from_config(
        project_name: Optional[str] = None,
        server_url: Optional[str] = None,
        user_token: Optional[str] = None,
        ssh_identity_file: Optional[PathLike] = None,
    ) -> "Client":
        """
        Creates a Client using the default configuration from `~/.dstack/config.yml` if it exists.

        Args:
            project_name: The name of the project, required if `server_url` and `user_token` are specified
            server_url: The dstack server URL (e.g. `http://localhost:3000/` or `https://sky.dstack.ai`)
            user_token: The dstack user token
            ssh_identity_file: The private SSH key path for SSH tunneling

        Returns:
            A client instance
        """
        if server_url is not None and user_token is not None:
            if project_name is None:
                raise ConfigurationError("The project name is not specified")
            api_client = APIClient(server_url, user_token)
        else:
            api_client, project_name = api_client_service.get_api_client(project_name=project_name)
        return Client(
            api_client=api_client,
            project_name=project_name,
            ssh_identity_file=ssh_identity_file,
        )

    @property
    def repos(self) -> RepoCollection:
        return self._repos

    @property
    def backends(self) -> BackendCollection:
        return self._backends

    @property
    def runs(self) -> RunCollection:
        return self._runs

    @property
    def client(self) -> APIClient:
        return self._client

    @property
    def project(self) -> str:
        return self._project

    @property
    def pool(self) -> PoolCollection:
        return self._pool
