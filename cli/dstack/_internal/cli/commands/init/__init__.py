from argparse import Namespace
from pathlib import Path
from typing import Optional

import giturlparse
from git.exc import InvalidGitRepositoryError

from dstack._internal.api.repos import InvalidRepoCredentialsError, get_local_repo_credentials
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, console
from dstack._internal.cli.config import config, get_hub_client
from dstack._internal.cli.errors import CLIError
from dstack._internal.core.repo import LocalRepo, RemoteRepo
from dstack._internal.core.userconfig import RepoUserConfig
from dstack._internal.utils.crypto import generage_rsa_key_pair


class InitCommand(BasicCommand):
    NAME = "init"
    DESCRIPTION = "Initialize the repo"

    def __init__(self, parser):
        super(InitCommand, self).__init__(parser)

    def register(self):
        add_project_argument(self._parser)
        self._parser.add_argument(
            "-t",
            "--token",
            metavar="OAUTH_TOKEN",
            help="An authentication token for Git",
            type=str,
            dest="gh_token",
        )
        self._parser.add_argument(
            "--git-identity",
            metavar="SSH_PRIVATE_KEY",
            help="A path to the private SSH key file for non-public repositories",
            type=str,
            dest="git_identity_file",
        )
        self._parser.add_argument(
            "--ssh-identity",
            metavar="SSH_PRIVATE_KEY",
            help="A path to the private SSH key file for SSH tunneling",
            type=Path,
            dest="ssh_identity_file",
        )
        self._parser.add_argument("--local", action="store_true", help="Do not use git")

    def _command(self, args: Namespace):
        try:
            if args.local:  # force fallback to LocalRepo
                raise InvalidGitRepositoryError()
            repo = RemoteRepo(local_repo_dir=Path.cwd())
            try:
                repo_credentials = get_local_repo_credentials(
                    repo_data=repo.repo_data,
                    identity_file=args.git_identity_file,
                    oauth_token=args.gh_token,
                    original_hostname=giturlparse.parse(repo.repo_url).resource,
                )
            except InvalidRepoCredentialsError as e:
                raise CLIError(e.message)
        except InvalidGitRepositoryError:
            repo = LocalRepo(repo_dir=Path.cwd())
            repo_credentials = None

        config.save_repo_user_config(
            RepoUserConfig(
                repo_id=repo.repo_ref.repo_id,
                repo_type=repo.repo_data.repo_type,
                ssh_key_path=get_ssh_keypair(
                    args.ssh_identity_file,
                    dstack_key_path=config.dstack_key_path(Path.cwd()),
                ),
            )
        )
        hub_client = get_hub_client(project_name=args.project)
        if repo_credentials is not None:
            hub_client.save_repo_credentials(repo_credentials)
        console.print(f"[green]OK[/]")


def get_ssh_keypair(
    key_path: Optional[Path], dstack_key_path: Optional[Path] = None
) -> Optional[str]:
    """Returns path to the private key if keypair exists"""
    if key_path is not None:
        key_path = key_path.expanduser().resolve()
        pub_key = (
            key_path
            if key_path.suffix == ".pub"
            else key_path.with_suffix(key_path.suffix + ".pub")
        )
        private_key = pub_key.with_suffix("")
        if pub_key.exists() and private_key.exists():
            return str(private_key)
        raise CLIError(
            f"Make sure valid keypair exists: {private_key}(.pub) and rerun `dstack init`"
        )

    if dstack_key_path is None:
        return None
    if not dstack_key_path.exists():
        generage_rsa_key_pair(private_key_path=dstack_key_path)
    return str(dstack_key_path)
