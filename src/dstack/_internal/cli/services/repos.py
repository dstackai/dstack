import argparse
from typing import Literal, Union, overload

import git

from dstack._internal.cli.services.configurators.base import ArgsParser
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.repos.local import LocalRepo
from dstack._internal.core.models.repos.remote import GitRepoURL, RemoteRepo, RepoError
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
    # Deprecated since 0.19.25
    parser.add_argument(
        "--local",
        action="store_true",
        help=argparse.SUPPRESS,
    )


def init_default_virtual_repo(api: Client) -> VirtualRepo:
    repo = VirtualRepo()
    api.repos.init(repo)
    return repo


@overload
def get_repo_from_dir(repo_dir: PathLike, local: Literal[False] = False) -> RemoteRepo: ...


@overload
def get_repo_from_dir(repo_dir: PathLike, local: Literal[True]) -> LocalRepo: ...


def get_repo_from_dir(repo_dir: PathLike, local: bool = False) -> Union[RemoteRepo, LocalRepo]:
    if local:
        return LocalRepo.from_dir(repo_dir)
    try:
        return RemoteRepo.from_dir(repo_dir)
    except git.InvalidGitRepositoryError:
        raise CLIError(
            f"Git repo not found: {repo_dir}\n"
            "Use `files` to mount an arbitrary directory:"
            " https://dstack.ai/docs/concepts/tasks/#files"
        )
    except RepoError as e:
        raise CLIError(str(e)) from e


def is_git_repo_url(value: str) -> bool:
    try:
        GitRepoURL.parse(value)
    except RepoError:
        return False
    return True
