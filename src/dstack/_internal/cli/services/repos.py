from pathlib import Path
from typing import Optional

from dstack._internal.cli.services.configurators.base import ArgsParser
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.repos.base import Repo, RepoType
from dstack._internal.core.models.repos.remote import GitRepoURL, RemoteRepo, RepoError
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.repos import get_default_branch
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
    parser.add_argument(
        "--ssh-identity",
        metavar="SSH_PRIVATE_KEY",
        help="The private SSH key path for SSH tunneling",
        type=Path,
        dest="ssh_identity_file",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Do not use Git",
    )


def init_repo(
    api: Client,
    repo_path: Optional[PathLike],
    repo_branch: Optional[str],
    repo_hash: Optional[str],
    local: bool,
    git_identity_file: Optional[PathLike],
    oauth_token: Optional[str],
    ssh_identity_file: Optional[PathLike],
) -> Repo:
    init = True
    if repo_path is None:
        init = False
        repo_path = Path.cwd()
    if Path(repo_path).exists():
        repo = api.repos.load(
            repo_dir=repo_path,
            local=local,
            init=init,
            git_identity_file=git_identity_file,
            oauth_token=oauth_token,
        )
        if ssh_identity_file:
            ConfigManager().save_repo_config(
                repo_path=repo.get_repo_dir_or_error(),
                repo_id=repo.repo_id,
                repo_type=RepoType(repo.run_repo_data.repo_type),
                ssh_key_path=ssh_identity_file,
            )
    elif isinstance(repo_path, str):
        try:
            GitRepoURL.parse(repo_path)
        except RepoError as e:
            raise CLIError("Invalid repo path") from e
        if repo_branch is None and repo_hash is None:
            repo_branch = get_default_branch(repo_path)
            if repo_branch is None:
                raise CLIError(
                    "Failed to automatically detect remote repo branch."
                    " Specify --repo-branch or --repo-hash."
                )
        repo = RemoteRepo.from_url(
            repo_url=repo_path,
            repo_branch=repo_branch,
            repo_hash=repo_hash,
        )
        api.repos.init(
            repo=repo,
            git_identity_file=git_identity_file,
            oauth_token=oauth_token,
        )
    else:
        raise CLIError("Invalid repo path")
    return repo


def init_default_virtual_repo(api: Client) -> VirtualRepo:
    repo = VirtualRepo()
    api.repos.init(repo)
    return repo
