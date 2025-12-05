import argparse
import os
from pathlib import Path
from typing import Optional

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.services.repos import (
    get_repo_from_dir,
    get_repo_from_url,
    is_git_repo_url,
    register_init_repo_args,
)
from dstack._internal.cli.utils.common import console
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
            "-P",
            "--repo",
            help=(
                "The repo to initialize. Can be a local path or a Git repo URL."
                " Defaults to the current working directory."
            ),
            dest="repo",
        )
        register_init_repo_args(self._parser)

    def _command(self, args: argparse.Namespace):
        super()._command(args)

        repo_path: Optional[Path] = None
        repo_url: Optional[str] = None
        repo_arg: Optional[str] = args.repo
        if repo_arg is not None:
            if is_git_repo_url(repo_arg):
                repo_url = repo_arg
            else:
                repo_path = Path(repo_arg).expanduser().resolve()
        else:
            repo_path = Path.cwd()

        if repo_url is not None:
            repo = get_repo_from_url(repo_url)
        elif repo_path is not None:
            repo = get_repo_from_dir(repo_path)
        else:
            assert False, "should not reach here"
        api = Client.from_config(project_name=args.project)
        api.repos.init(
            repo=repo,
            git_identity_file=args.git_identity_file,
            oauth_token=args.gh_token,
        )
        console.print("OK")
