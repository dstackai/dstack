from pathlib import Path
from typing import Optional, Union

from git import InvalidGitRepositoryError

from dstack._internal.core.errors import ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo
from dstack._internal.core.models.repos.base import Repo, RepoType
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.repos import (
    InvalidRepoCredentialsError,
    get_local_repo_credentials,
    load_repo,
)
from dstack._internal.utils.crypto import generate_rsa_key_pair
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike
from dstack.api.server import APIClient

logger = get_logger(__name__)


class RepoCollection:
    """
    Operations with repos
    """

    def __init__(self, api_client: APIClient, project: str):
        self._api_client = api_client
        self._project = project

    def init(
        self,
        repo: Repo,
        git_identity_file: Optional[PathLike] = None,
        oauth_token: Optional[str] = None,
    ):
        """
        Initializes the repo and configures its credentials in the project.
        Must be invoked before mounting the repo to a run.

        Example:

        ```python
        repo=RemoteRepo.from_url(
            repo_url="https://github.com/dstackai/dstack-examples",
            repo_branch="main",
        )
        client.repos.init(repo)
        ```

        By default, it uses the default Git credentials configured on the machine.
        You can override these credentials via the `git_identity_file` or `oauth_token` arguments of the `init` method.

        Once the repo is initialized, you can pass the repo object to the run:

        ```python
        run = client.runs.apply_configuration(
            configuration=...,
            repo=repo,
        )
        ```

        Args:
            repo: The repo to initialize.
            git_identity_file: The private SSH key path for accessing the remote repo.
            oauth_token: The GitHub OAuth token to access the remote repo.
        """
        creds = None
        if isinstance(repo, RemoteRepo):
            try:
                creds = get_local_repo_credentials(
                    repo_url=repo.repo_url,
                    identity_file=git_identity_file,
                    oauth_token=oauth_token,
                )
            except InvalidRepoCredentialsError as e:
                raise ConfigurationError(*e.args)
        self._api_client.repos.init(self._project, repo.repo_id, repo.get_repo_info(), creds)

    def load(
        self,
        repo_dir: PathLike,
        local: bool = False,
        init: bool = False,
        git_identity_file: Optional[PathLike] = None,
        oauth_token: Optional[str] = None,
    ) -> Union[RemoteRepo, LocalRepo]:
        """
        Loads the repo from the local directory using global config

        Args:
            repo_dir: Repo root directory.
            local: Do not try to load `RemoteRepo` first.
            init: Initialize the repo if it's not initialized.
            git_identity_file: Path to an SSH private key to access the remote repo.
            oauth_token: GitHub OAuth token to access the remote repo.

        Raises:
            ConfigurationError: If the repo is not initialized and `init` is `False`.

        Returns:
            repo: Initialized repo.
        """
        config = ConfigManager()
        if not init:
            logger.debug("Loading repo config")
            repo_config = config.get_repo_config(repo_dir)
            if repo_config is None:
                raise ConfigurationError(
                    "The repo is not initialized."
                    " Run `dstack init` to initialize the current directory as a repo or specify `--repo`."
                )
            repo = load_repo(repo_config)
            try:
                self._api_client.repos.get(self._project, repo.repo_id, include_creds=False)
            except ResourceNotExistsError:
                raise ConfigurationError(
                    "The repo is not initialized."
                    " Run `dstack init` to initialize the current directory as a repo or specify `--repo`."
                )
        else:
            logger.debug("Initializing repo")
            repo = LocalRepo(repo_dir=repo_dir)  # default
            if not local:
                try:
                    repo = RemoteRepo.from_dir(repo_dir)
                except InvalidGitRepositoryError:
                    pass  # use default
            self.init(repo, git_identity_file, oauth_token)
            config.save_repo_config(
                repo.get_repo_dir_or_error(),
                repo.repo_id,
                RepoType(repo.run_repo_data.repo_type),
                get_ssh_keypair(None, config.dstack_key_path),
            )
        return repo

    def is_initialized(
        self,
        repo: Repo,
    ) -> bool:
        """
        Checks if the remote repo is initialized in the project

        Args:
            repo: The repo to check.

        Returns:
            Whether the repo is initialized or not.
        """
        try:
            self._api_client.repos.get(self._project, repo.repo_id, include_creds=False)
            return True
        except ResourceNotExistsError:
            return False


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
