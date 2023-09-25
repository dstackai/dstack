from typing import Optional, Union

from git import InvalidGitRepositoryError

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo
from dstack._internal.core.services.configs import ConfigManager, get_api_client
from dstack._internal.core.services.repos import load_repo
from dstack._internal.utils.path import PathLike
from dstack.api._public.backends import BackendCollection
from dstack.api._public.repos import RepoCollection
from dstack.api._public.runs import RunCollection
from dstack.api.server import APIClient


class Client:
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
        :param api_client: low-level server API client
        :param project_name: project name used for runs
        :param repo_dir: path to the repo
        :param repo: repo used for runs
        :param git_identity_file: private SSH key to access remote repo, used only if `init` is True
        :param oauth_token: GitHub OAuth token to access remote repo, used only if `init` is True
        :param ssh_identity_file: SSH keypair to access instances
        :param init: initialize the repo first
        """
        self._repos = RepoCollection(api_client, project_name, repo)
        self._backends = BackendCollection(api_client, project_name)
        # TODO require ssh identity file
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
        Creates a Client using global config ~/.dstack/config.yaml
        :param repo_dir: path to the repo
        :param project_name: name of the project, required if `server_url` and `user_token` are specified
        :param server_url: dstack server url, e.g. http://localhost:3000/
        :param user_token: dstack user token
        :param git_identity_file: path to a private SSH key to access remote repo
        :param oauth_token: GitHub OAuth token to access remote repo
        :param ssh_identity_file: SSH keypair to access instances
        :param local_repo: load repo as local, has an effect only if `init` is True
        :param init: initialize the repo first
        :return: dstack Client
        """
        if not init:
            repo_config = ConfigManager().get_repo_config(repo_dir)
            if repo_config is None:
                raise ConfigurationError(f"The repo is not initialized")
            repo = load_repo(repo_config)
        else:
            repo = LocalRepo(repo_dir=repo_dir)  # default
            if not local_repo:
                try:
                    repo = RemoteRepo(local_repo_dir=repo_dir)
                except InvalidGitRepositoryError:
                    pass  # use default
        if server_url is not None and user_token is not None:
            if project_name is None:
                raise ConfigurationError(f"The project name is not specified")
            api_client = APIClient(server_url, user_token)
        else:
            api_client, project_name = get_api_client(project_name=project_name)
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
