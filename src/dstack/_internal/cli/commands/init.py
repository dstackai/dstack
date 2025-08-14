import argparse
import os
from pathlib import Path

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.services.repos import init_repo, register_init_repo_args
from dstack._internal.cli.utils.common import configure_logging, confirm_ask, console, warn
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.repos.base import RepoType
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
        register_init_repo_args(self._parser)
        # Deprecated since 0.19.25, ignored
        self._parser.add_argument(
            "--ssh-identity",
            metavar="SSH_PRIVATE_KEY",
            help=argparse.SUPPRESS,
            type=Path,
            dest="ssh_identity_file",
        )
        # A hidden mode for transitional period only, remove it with local repos
        self._parser.add_argument(
            "--remove",
            help=argparse.SUPPRESS,
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        configure_logging()
        if args.remove:
            config_manager = ConfigManager()
            repo_path = Path.cwd()
            repo_config = config_manager.get_repo_config(repo_path)
            if repo_config is None:
                raise ConfigurationError("The repo is not initialized, nothing to remove")
            if repo_config.repo_type != RepoType.LOCAL:
                raise ConfigurationError("`dstack init --remove` is for local repos only")
            console.print(
                f"You are about to remove the local repo {repo_path}\n"
                "Only the record about the repo will be removed,"
                " the repo files will remain intact\n"
            )
            if not confirm_ask("Remove the local repo?"):
                return
            config_manager.delete_repo_config(repo_config.repo_id)
            config_manager.save()
            console.print("Local repo has been removed")
            return
        api = Client.from_config(
            project_name=args.project, ssh_identity_file=args.ssh_identity_file
        )
        if args.local:
            warn(
                "Local repos are deprecated since 0.19.25 and will be removed soon."
                " Consider using `files` instead: https://dstack.ai/docs/concepts/tasks/#files"
            )
        if args.ssh_identity_file:
            warn(
                "`--ssh-identity` in `dstack init` is deprecated and ignored since 0.19.25."
                " Use this option with `dstack apply` and `dstack attach` instead"
            )
        init_repo(
            api=api,
            repo_path=Path.cwd(),
            repo_branch=None,
            repo_hash=None,
            local=args.local,
            git_identity_file=args.git_identity_file,
            oauth_token=args.gh_token,
        )
        console.print("OK")
