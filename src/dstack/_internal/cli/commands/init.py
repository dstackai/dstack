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
from dstack._internal.cli.utils.common import configure_logging, confirm_ask, console, warn
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.services.configs import ConfigManager
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
        # Deprecated since 0.19.25, ignored
        self._parser.add_argument(
            "--ssh-identity",
            metavar="SSH_PRIVATE_KEY",
            help=argparse.SUPPRESS,
            type=Path,
            dest="ssh_identity_file",
        )
        # A hidden mode for transitional period only, remove it with repos in `config.yml`
        self._parser.add_argument(
            "--remove",
            help=argparse.SUPPRESS,
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        configure_logging()

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

        if args.remove:
            if repo_url is not None:
                raise ConfigurationError(f"Local path expected, got URL: {repo_url}")
            assert repo_path is not None
            config_manager = ConfigManager()
            repo_config = config_manager.get_repo_config(repo_path)
            if repo_config is None:
                raise ConfigurationError("Repo record not found, nothing to remove")
            console.print(
                f"You are about to remove the repo {repo_path}\n"
                "Only the record about the repo will be removed,"
                " the repo files will remain intact\n"
            )
            if not confirm_ask("Remove the repo?"):
                return
            config_manager.delete_repo_config(repo_config.repo_id)
            config_manager.save()
            console.print("Repo has been removed")
            return

        local: bool = args.local
        if local:
            warn(
                "Local repos are deprecated since 0.19.25 and will be removed soon. Consider"
                " using [code]files[/code] instead: https://dstack.ai/docs/concepts/tasks/#files"
            )
        if args.ssh_identity_file:
            warn(
                "[code]--ssh-identity[/code] in [code]dstack init[/code] is deprecated and ignored"
                " since 0.19.25. Use this option with [code]dstack apply[/code]"
                " and [code]dstack attach[/code] instead"
            )

        if repo_url is not None:
            # Dummy repo branch to avoid autodetection that fails on private repos.
            # We don't need branch/hash for repo_id anyway.
            repo = get_repo_from_url(repo_url, repo_branch="master")
        elif repo_path is not None:
            repo = get_repo_from_dir(repo_path, local=local)
        else:
            assert False, "should not reach here"
        api = Client.from_config(project_name=args.project)
        api.repos.init(
            repo=repo,
            git_identity_file=args.git_identity_file,
            oauth_token=args.gh_token,
        )
        console.print("OK")
