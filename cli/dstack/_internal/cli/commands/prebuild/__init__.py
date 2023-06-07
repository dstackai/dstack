import argparse
import os
import sys

from jsonschema import ValidationError

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.commands.run import _poll_run, _read_ssh_key_pub, configurations
from dstack._internal.cli.common import add_project_argument, check_init, console, print_runs
from dstack._internal.cli.config import config, get_hub_client
from dstack._internal.core.error import RepoNotInitializedError
from dstack._internal.core.job import JobStatus


class PrebuildCommand(BasicCommand):
    NAME = "prebuild"
    DESCRIPTION = "Prebuild environment"

    @check_init
    def _command(self, args: argparse.Namespace):
        (provider_name, provider_data, project_name,) = configurations.parse_configuration_file(
            args.working_dir, args.file_name, args.profile_name
        )
        provider_data["prebuild"] = "prebuild-only"

        if args.project:
            project_name = args.project
        try:
            hub_client = get_hub_client(project_name=project_name)
            if (
                hub_client.repo.repo_data.repo_type != "local"
                and not hub_client.get_repo_credentials()
            ):
                raise RepoNotInitializedError("No credentials", project_name=project_name)

            if not config.repo_user_config.ssh_key_path:
                ssh_pub_key = None
            else:
                ssh_pub_key = _read_ssh_key_pub(config.repo_user_config.ssh_key_path)

            run_name, jobs = hub_client.run_provider(
                provider_name,
                provider_data=provider_data,
                ssh_pub_key=ssh_pub_key,
                args=args,
            )
            runs = list_runs_hub(hub_client, run_name=run_name)
            print_runs(runs)
            run = runs[0]
            if run.status == JobStatus.FAILED:
                console.print("\nProvisioning failed\n")
                exit(1)
            _poll_run(
                hub_client,
                jobs,
                ssh_key=config.repo_user_config.ssh_key_path,
                watcher=None,
            )
        except ValidationError as e:
            sys.exit(
                f"There a syntax error in one of the files inside the {os.getcwd()}/.dstack/workflows directory:\n\n{e}"
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
