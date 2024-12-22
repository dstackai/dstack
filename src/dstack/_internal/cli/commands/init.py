import argparse
import os
from pathlib import Path

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.services.repos import init_repo, register_init_repo_args
from dstack._internal.cli.utils.common import configure_logging, console
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
        register_init_repo_args(self._parser)

    def _command(self, args: argparse.Namespace):
        configure_logging()
        api = Client.from_config(
            project_name=args.project, ssh_identity_file=args.ssh_identity_file
        )
        init_repo(
            api=api,
            repo_path=Path.cwd(),
            repo_branch=None,
            repo_hash=None,
            local=args.local,
            git_identity_file=args.git_identity_file,
            oauth_token=args.gh_token,
            ssh_identity_file=args.ssh_identity_file,
        )
        console.print("OK")
