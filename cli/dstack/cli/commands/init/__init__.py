from argparse import Namespace
from pathlib import Path
from typing import Optional

import giturlparse

from dstack.api.backend import list_backends
from dstack.api.repos import get_local_repo_credentials, test_repo_credentials
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, console
from dstack.cli.config import config
from dstack.core.repo import RemoteRepo
from dstack.core.userconfig import RepoUserConfig


def get_ssh_keypair(key_path: Optional[str], default: str = "~/.ssh/id_rsa") -> Optional[str]:
    """Returns path to the private key if keypair exists"""
    key_path = Path(key_path or default).expanduser().resolve()
    pub_key = (
        key_path if key_path.suffix == ".pub" else key_path.with_suffix(key_path.suffix + ".pub")
    )
    private_key = pub_key.with_suffix("")
    if pub_key.exists() and private_key.exists():
        return str(private_key)


class InitCommand(BasicCommand):
    NAME = "init"
    DESCRIPTION = "Authorize dstack to access the current Git repo"

    def __init__(self, parser):
        super(InitCommand, self).__init__(parser)

    def register(self):
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
            type=str,
            dest="ssh_identity_file",
        )

    @check_config
    @check_git
    @check_backend
    def _command(self, args: Namespace):
        repo = RemoteRepo(local_repo_dir=Path.cwd())
        repo_credentials = get_local_repo_credentials(
            giturlparse.parse(repo.repo_url).resource,  # hostname before mapping from SSH config
            identity_file=args.git_identity_file,
            oauth_token=args.gh_token,
        )
        test_repo_credentials(repo.repo_data, repo_credentials)

        config.repo_user_config = RepoUserConfig(
            repo_id=repo.repo_ref.repo_id,
            repo_user_id=repo.repo_ref.repo_user_id,
            ssh_key_path=get_ssh_keypair(args.ssh_identity_file),
        )

        for backend in list_backends(repo):
            backend.save_repo_credentials(repo_credentials)
            status = (
                "[yellow]WARNING[/]"
                if config.repo_user_config.ssh_key_path is None
                else "[green]OK[/]"
            )
            console.print(f"{status} [gray58](backend: {backend.name})[/]")
        if config.repo_user_config.ssh_key_path is None:
            console.print(
                f"[red]SSH is not enabled. To enable it, make sure `{args.ssh_identity_file or '~/.ssh/id_rsa'}` exists or call `dstack init --ssh-identity PATH`[/]"
            )
