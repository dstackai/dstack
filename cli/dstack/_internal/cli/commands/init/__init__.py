from argparse import Namespace
from pathlib import Path

from dstack._internal.api.repos import InvalidRepoCredentialsError
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.errors import CLIError
from dstack._internal.cli.utils.common import add_project_argument, console
from dstack._internal.cli.utils.config import get_hub_client
from dstack._internal.cli.utils.init import init_repo


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
        hub_client = get_hub_client(project_name=args.project, local_repo=args.local)
        try:
            init_repo(
                hub_client,
                git_identity_file=args.git_identity_file,
                oauth_token=args.gh_token,
                ssh_identity_file=args.ssh_identity_file,
            )
            console.print(f"[green]OK[/]")
        except InvalidRepoCredentialsError as e:
            raise CLIError(e.message)
