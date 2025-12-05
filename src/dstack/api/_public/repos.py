from typing import Literal, Optional, Union, overload

from git import InvalidGitRepositoryError

from dstack._internal.core.errors import ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.repos import (
    LocalRepo,
    RemoteRepo,
    RemoteRepoCreds,
    Repo,
    RepoHead,
    RepoHeadWithCreds,
)
from dstack._internal.core.services.repos import (
    InvalidRepoCredentialsError,
    get_repo_creds_and_default_branch,
)
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
        creds: Optional[RemoteRepoCreds] = None,
    ):
        """
        Initializes the repo and configures its credentials in the project.
        Must be invoked before mounting the repo to a run.

        Example:

        ```python
        repo = RemoteRepo.from_url(
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
            creds: Optional prepared repo credentials. If specified, both `git_identity_file`
                and `oauth_token` are ignored.
        """
        if isinstance(repo, LocalRepo):
            raise ConfigurationError(
                "Local repositories are not supported since 0.20.0. Use `files` to mount"
                " an arbitrary directory: https://dstack.ai/docs/concepts/tasks/#files"
            )
        if creds is None and isinstance(repo, RemoteRepo):
            assert repo.repo_url is not None
            try:
                creds, _ = get_repo_creds_and_default_branch(
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
    ) -> RemoteRepo:
        # """
        # Loads the repo from the local directory using global config

        # Args:
        #     repo_dir: Repo root directory.
        #     local: Do not try to load `RemoteRepo` first.
        #     init: Initialize the repo if it's not initialized.
        #     git_identity_file: Path to an SSH private key to access the remote repo.
        #     oauth_token: GitHub OAuth token to access the remote repo.

        # Raises:
        #     ConfigurationError: If the repo is not initialized and `init` is `False`.

        # Returns:
        #     repo: Initialized repo.
        # """
        logger.warning(
            "The load() method is deprecated, use RemoteRepo directly:"
            " https://dstack.ai/docs/reference/api/python/#dstack.api.RemoteRepo"
        )
        if local:
            raise ConfigurationError(
                "Local repositories are not supported since 0.20.0. Use `files` to mount"
                " an arbitrary directory: https://dstack.ai/docs/concepts/tasks/#files"
            )
        if not init:
            raise ConfigurationError(
                "Repo config has been removed in 0.20.0,"
                " this method can now only be used with init=True"
            )
        logger.debug("Initializing repo")
        try:
            repo = RemoteRepo.from_dir(repo_dir)
        except InvalidGitRepositoryError:
            raise ConfigurationError(
                f"Git repo not found: {repo_dir}. Use `files` to mount an arbitrary"
                " directory: https://dstack.ai/docs/concepts/tasks/#files"
            )
        self.init(repo, git_identity_file, oauth_token)
        return repo

    def is_initialized(
        self,
        repo: Repo,
        by_user: bool = False,
    ) -> bool:
        """
        Checks if the repo is initialized in the project

        Args:
            repo: The repo to check.
            by_user: Require the remote repo to be initialized by the user, that is, to have
                the user's credentials. Ignored for other repo types.

        Returns:
            Whether the repo is initialized or not.
        """
        if isinstance(repo, RemoteRepo) and by_user:
            return self._is_initialized_by_user(repo)
        try:
            self._api_client.repos.get(self._project, repo.repo_id)
            return True
        except ResourceNotExistsError:
            return False

    def _is_initialized_by_user(self, repo: RemoteRepo) -> bool:
        try:
            repo_head = self._api_client.repos.get_with_creds(self._project, repo.repo_id)
        except ResourceNotExistsError:
            return False
        # This works because:
        # - RepoCollection.init() always submits RemoteRepoCreds for remote repos, even if
        #   the repo is public
        # - Server returns creds only if there is RepoCredsModel for the user (or legacy
        #   shared creds in RepoModel)
        # TODO: add an API method with the same logic returning a bool value?
        return repo_head.repo_creds is not None

    @overload
    def get(self, repo_id: str, *, with_creds: Literal[False] = False) -> Optional[RepoHead]: ...

    @overload
    def get(self, repo_id: str, *, with_creds: Literal[True]) -> Optional[RepoHeadWithCreds]: ...

    def get(
        self, repo_id: str, *, with_creds: bool = False
    ) -> Optional[Union[RepoHead, RepoHeadWithCreds]]:
        """
        Returns the repo by `repo_id`

        Args:
            repo_id: The repo ID.
            with_creds: include repo credentials in the response.

        Returns:
            The repo or `None` if the repo is not found.
        """
        method = self._api_client.repos.get
        if with_creds:
            method = self._api_client.repos.get_with_creds
        try:
            return method(self._project, repo_id)
        except ResourceNotExistsError:
            return None
