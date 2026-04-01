from pathlib import Path

from dstack._internal.cli.services.configurators.base import ArgsParser
from dstack._internal.core.errors import (
    CLIError,
    RepoDetachedHeadError,
    RepoError,
    RepoInvalidGitRepositoryError,
)
from dstack._internal.core.models.repos.remote import GitRepoURL, RemoteRepo
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack._internal.utils.path import PathLike
from dstack.api._public import Client


def register_init_repo_args(parser: ArgsParser):
    parser.add_argument(
        "-t",
        "--token",
        metavar="OAUTH_TOKEN",
        help="An authentication token to access a private Git repo",
        type=str,
        dest="gh_token",
    )
    parser.add_argument(
        "--git-identity",
        metavar="SSH_PRIVATE_KEY",
        help="The private SSH key path to access a private Git repo",
        type=str,
        dest="git_identity_file",
    )


def init_default_virtual_repo(api: Client) -> VirtualRepo:
    repo = VirtualRepo()
    api.repos.init(repo)
    return repo


def get_repo_from_dir(repo_dir: PathLike) -> RemoteRepo:
    repo_dir = Path(repo_dir)
    if not repo_dir.exists():
        raise CLIError(f"Path does not exist: {repo_dir}")
    if not repo_dir.is_dir():
        raise CLIError(f"Path is not a directory: {repo_dir}")
    try:
        return RemoteRepo.from_dir(repo_dir)
    except RepoInvalidGitRepositoryError:
        raise CLIError(
            f"Git repo not found: {repo_dir}\n"
            "Use `files` to mount an arbitrary directory:"
            " https://dstack.ai/docs/concepts/tasks/#files"
        )
    except RepoDetachedHeadError:
        raise CLIError(f"Git repo in 'detached HEAD' state: {repo_dir}\nCheck out to a branch")
    except RepoError as e:
        raise CLIError(str(e)) from e


def get_repo_from_url(repo_url: str) -> RemoteRepo:
    try:
        return RemoteRepo.from_url(repo_url)
    except RepoError as e:
        raise CLIError(str(e)) from e


def is_git_repo_url(value: str) -> bool:
    try:
        GitRepoURL.parse(value)
    except RepoError:
        return False
    return True
