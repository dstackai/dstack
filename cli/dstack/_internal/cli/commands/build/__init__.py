import argparse

from rich.prompt import Confirm

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.commands.run import _poll_run, _print_run_plan, _read_ssh_key_pub
from dstack._internal.cli.common import add_project_argument, check_init, console
from dstack._internal.cli.config import config, get_hub_client
from dstack._internal.cli.configuration import load_configuration
from dstack._internal.core.error import RepoNotInitializedError


class BuildCommand(BasicCommand):
    NAME = "build"
    DESCRIPTION = "Pre-build the environment"

    @check_init
    def _command(self, args: argparse.Namespace):
        configurator = load_configuration(args.working_dir, args.file_name, args.profile_name)
        configurator.build_policy = "build-only"

        project_name = None
        if args.project:
            project_name = args.project
        elif configurator.profile.project:
            project_name = configurator.profile.project

        hub_client = get_hub_client(project_name=project_name)
        if (
            hub_client.repo.repo_data.repo_type != "local"
            and not hub_client.get_repo_credentials()
        ):
            raise RepoNotInitializedError("No credentials", project_name=project_name)

        if not config.repo_user_config.ssh_key_path:
            ssh_key_pub = None
        else:
            ssh_key_pub = _read_ssh_key_pub(config.repo_user_config.ssh_key_path)

        configurator_args, run_args = configurator.get_parser().parse_known_args(
            args.args + args.unknown
        )
        configurator.apply_args(configurator_args)

        run_plan = hub_client.get_run_plan(configurator)
        console.print("dstack will execute the following plan:\n")
        _print_run_plan(configurator.configuration_path, run_plan)
        if not args.yes and not Confirm.ask("Continue?"):
            console.print("\nExiting...")
            exit(0)
        console.print("\nProvisioning...\n")

        run_name, jobs = hub_client.run_configuration(
            configurator=configurator,
            ssh_key_pub=ssh_key_pub,
            run_args=run_args,
        )
        runs = list_runs_hub(hub_client, run_name=run_name)
        run = runs[0]
        _poll_run(
            hub_client,
            run,
            jobs,
            ssh_key=config.repo_user_config.ssh_key_path,
            watcher=None,
        )

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        self._parser.add_argument(
            "working_dir",
            metavar="WORKING_DIR",
            type=str,
            help="The working directory of the run",
        )
        self._parser.add_argument(
            "-f",
            "--file",
            metavar="FILE",
            help="The path to the run configuration file. Defaults to WORKING_DIR/.dstack.yml.",
            type=str,
            dest="file_name",
        )
        add_project_argument(self._parser)
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for plan confirmation",
            action="store_true",
        )
        self._parser.add_argument(
            "--profile",
            metavar="PROFILE",
            help="The name of the profile",
            type=str,
            dest="profile_name",
        )
        self._parser.add_argument(
            "args",
            metavar="ARGS",
            nargs=argparse.ZERO_OR_MORE,
            help="Run arguments",
        )
