from pathlib import Path
from typing import Optional, Union

from git import InvalidGitRepositoryError

import dstack._internal.core.services.api_client as api_client_service
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.repos import load_repo
from dstack._internal.utils.crypto import generate_rsa_key_pair
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike
from dstack.api._public.backends import BackendCollection
from dstack.api._public.repos import RepoCollection
from dstack.api._public.runs import RunCollection
from dstack.api.server import APIClient

logger = get_logger(__name__)


class Client:
    """
    High-level API client for interacting with dstack server

    Attributes:
        repos: operations with repos
        backends: operations with backends
        runs: operations with runs
        client: low-level server API client
        project: project name
    """

    def __init__(
        self,
        api_client: APIClient,
        project_name: str,
        repo_dir: PathLike,
        repo: Union[RemoteRepo, LocalRepo],
        git_identity_file: Optional[PathLike] = None,
        oauth_token: Optional[str] = None,
        ssh_identity_file: Optional[PathLike] = None,
        init: bool = True,
    ):
        """
        Args:
            api_client: low-level server API client
            project_name: project name used for runs
            repo_dir: path to the repo
            repo: repo used for runs
            git_identity_file: private SSH key to access remote repo, used only if `init` is True
            oauth_token: GitHub OAuth token to access remote repo, used only if `init` is True
            ssh_identity_file: SSH keypair to access instances
            init: initialize the repo first
        """
        self._client = api_client
        self._project = project_name
        self._repos = RepoCollection(api_client, project_name, repo)
        self._backends = BackendCollection(api_client, project_name)
        self._runs = RunCollection(api_client, project_name, repo_dir, repo, ssh_identity_file)

        if init:
            self.repos.init(git_identity_file, oauth_token)
        else:
            if not self.repos.is_initialized():
                raise ConfigurationError(f"The repo is not initialized")

    @staticmethod
    def from_config(
        repo_dir: PathLike,
        project_name: Optional[str] = None,
        server_url: Optional[str] = None,
        user_token: Optional[str] = None,
        git_identity_file: Optional[PathLike] = None,
        oauth_token: Optional[str] = None,
        ssh_identity_file: Optional[PathLike] = None,
        local_repo: bool = False,
        init: bool = True,
    ) -> "Client":
        """
        Creates a Client using global config `~/.dstack/config.yaml`

        Args:
            repo_dir: path to the repo
            project_name: name of the project, required if `server_url` and `user_token` are specified
            server_url: dstack server url, e.g. `http://localhost:3000/`
            user_token: dstack user token
            git_identity_file: path to a private SSH key to access remote repo
            oauth_token: GitHub OAuth token to access remote repo
            ssh_identity_file: SSH keypair to access instances
            local_repo: load repo as local, has an effect only if `init` is True
            init: initialize the repo first

        Returns:
            dstack Client
        """
        config = ConfigManager()
        if not init:
            logger.debug("Loading repo config")
            repo_config = config.get_repo_config(repo_dir)
            if repo_config is None:
                raise ConfigurationError(f"The repo is not initialized")
            repo = load_repo(repo_config)
            if ssh_identity_file is None:
                ssh_identity_file = repo_config.ssh_key_path
        else:
            logger.debug("Initializing repo")
            repo = LocalRepo(repo_dir=repo_dir)  # default
            if not local_repo:
                try:
                    repo = RemoteRepo(local_repo_dir=repo_dir)
                except InvalidGitRepositoryError:
                    pass  # use default
            ssh_identity_file = get_ssh_keypair(ssh_identity_file, config.dstack_key_path)
            config.save_repo_config(
                repo_dir, repo.repo_id, RepoType(repo.run_repo_data.repo_type), ssh_identity_file
            )
        if server_url is not None and user_token is not None:
            if project_name is None:
                raise ConfigurationError(f"The project name is not specified")
            api_client = APIClient(server_url, user_token)
        else:
            api_client, project_name = api_client_service.get_api_client(project_name=project_name)
        return Client(
            api_client,
            project_name,
            repo_dir,
            repo,
            git_identity_file,
            oauth_token,
            ssh_identity_file,
            init,
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


def get_ssh_keypair(key_path: Optional[PathLike], dstack_key_path: Path) -> str:
    """Returns a path to the private key"""
    if key_path is not None:
        key_path = Path(key_path).expanduser().resolve()
        pub_key = (
            key_path
            if key_path.suffix == ".pub"
            else key_path.with_suffix(key_path.suffix + ".pub")
        )
        private_key = pub_key.with_suffix("")
        if pub_key.exists() and private_key.exists():
            return str(private_key)
        raise ConfigurationError(f"Make sure valid keypair exists: {private_key}(.pub)")

    if not dstack_key_path.exists():
        generate_rsa_key_pair(private_key_path=dstack_key_path)
    return str(dstack_key_path)
