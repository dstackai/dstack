import argparse
from pathlib import Path

from dstack._internal.cli.commands import BaseCommand
from dstack.api import Client


class InitCommand(BaseCommand):
    NAME = "init"
    DESCRIPTION = "Initialize the repo"

    def _command(self, args: argparse.Namespace):
        Client.from_config(
            Path.cwd(),
            args.project,
            git_identity_file=args.git_identity_file,
            oauth_token=args.gh_token,
            ssh_identity_file=args.ssh_identity_file,
            local_repo=args.local,
            init=True,
        )
        print("OK")

    def _register(self):
        self._parser.add_argument("--project")
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
