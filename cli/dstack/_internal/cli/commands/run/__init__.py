import argparse
import os
from argparse import Namespace

from rich.prompt import Confirm

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.utils.common import add_project_argument, check_init, console
from dstack._internal.cli.utils.config import config, get_hub_client
from dstack._internal.cli.utils.configuration import load_configuration
from dstack._internal.cli.utils.run import (
    get_run_plan,
    poll_run,
    print_run_plan,
    run_configuration,
)
from dstack._internal.cli.utils.watcher import Watcher
from dstack._internal.configurators.ports import PortUsedError


class RunCommand(BasicCommand):
    NAME = "run"
    DESCRIPTION = "Run a configuration"

    def __init__(self, parser):
        super().__init__(parser, store_help=False)

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
        self._parser.add_argument(
            "-n",
            "--name",
            help="The name of the run. If not specified, a random name is assigned.",
        )
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for plan confirmation",
            action="store_true",
        )
        self._parser.add_argument(
            "-d",
            "--detach",
            help="Do not poll logs and run status",
            action="store_true",
        )
        self._parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable auto-reload",
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
            "--max-offers",
            help="The maximum number of best offers shown in run plan",
            type=int,
            default=3,
        )
        self._parser.add_argument(
            "args",
            metavar="ARGS",
            nargs=argparse.ZERO_OR_MORE,
            help="Run arguments",
        )

    @check_init
    def _command(self, args: Namespace):
        configurator = load_configuration(args.working_dir, args.file_name, args.profile_name)

        project_name = None
        if args.project:
            project_name = args.project

        watcher = Watcher(os.getcwd())
        try:
            if args.reload:
                watcher.start()
            hub_client = get_hub_client(project_name=project_name)
            configurator_args, run_args = configurator.get_parser().parse_known_args(
                args.args + args.unknown
            )
            configurator.apply_args(configurator_args)

            run_plan = get_run_plan(hub_client, configurator, args.name)
            job_plan = run_plan.job_plans[0]
            console.print("dstack will execute the following plan:\n")
            print_run_plan(configurator, run_plan, args.max_offers)
            if len(job_plan.candidates) == 0:
                console.print(
                    f"No instances matching requirements ({job_plan.job.requirements.pretty_format()})."
                )
                if job_plan.job.retry_active():
                    console.print("The run will be resubmitted according to retry policy.")
                else:
                    exit(1)
            if not args.yes and not Confirm.ask("Continue?"):
                console.print("\nExiting...")
                exit(0)
            console.print("\nProvisioning...\n")
            repo_user_config = config.repo_user_config(os.getcwd())
            run_name, jobs, ports_locks = run_configuration(
                hub_client,
                configurator,
                args.name,
                run_plan,
                not args.detach,
                run_args,
                repo_user_config,
            )
            runs = list_runs_hub(hub_client, run_name=run_name)
            run = runs[0]
            if not args.detach:
                poll_run(
                    hub_client,
                    run,
                    jobs,
                    ssh_key=repo_user_config.ssh_key_path,
                    watcher=watcher,
                    ports_locks=ports_locks,
                )
        except PortUsedError as e:
            exit(f"\n{e.message}")
        finally:
            if watcher.is_alive():
                watcher.stop()
                watcher.join()
