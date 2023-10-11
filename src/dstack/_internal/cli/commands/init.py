import argparse
import os
from pathlib import Path

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import cli_error, configure_logging, console
from dstack._internal.core.errors import ConfigurationError
from dstack.api import Client


class InitCommand(BaseCommand):
    NAME = "init"
    DESCRIPTION = "Initialize the repo"

    def _register(self):
        self._parser.add_argument(
            "--project",
            help="The name of the project",
            default=os.getenv("DSTACK_PROJECT"),
        )
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
        self._parser.add_argument(
            "--local",
            action="store_true",
            help="Do not use git",
        )

    def _command(self, args: argparse.Namespace):
        configure_logging()
        try:
            Client.from_config(
                Path.cwd(),
                args.project,
                git_identity_file=args.git_identity_file,
                oauth_token=args.gh_token,
                ssh_identity_file=args.ssh_identity_file,
                local_repo=args.local,
                init=True,
            )
        except ConfigurationError as e:
            raise cli_error(e)
        console.print("OK")
