import argparse
import logging
import sys
from pathlib import Path

from rich.prompt import Confirm

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.run import print_run_plan
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.services.configs.configuration import find_configuration_file
from dstack._internal.core.services.configs.profile import load_profile
from dstack.api import Client


class RunCommand(BaseCommand):
    NAME = "run"
    DESCRIPTION = "Run .dstack.yml configuration"

    def _register(self):
        # TODO custom help action
        # self._parser.add_argument("-h", "--help", nargs="?", choices=("task", "dev-environment", "service"))
        self._parser.add_argument("working_dir")
        self._parser.add_argument("-f", "--file", type=Path, dest="configuration_file")
        self._parser.add_argument("--profile")  # TODO env var default
        self._parser.add_argument("--project")  # TODO env var default
        self._parser.add_argument(
            "-n",
            "--name",
            dest="run_name",
            help="The name of the run. If not specified, a random name is assigned.",
        )
        self._parser.add_argument(
            "-d",
            "--detach",
            help="Do not poll logs and run status",
            action="store_true",
        )
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for plan confirmation",
            action="store_true",
        )
        self._parser.add_argument(
            "--backend",
            action="append",
            dest="backends",
            help="The backends that will be tried for provisioning",
        )

    def _command(self, args: argparse.Namespace):
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

        try:
            api = Client.from_config(Path.cwd(), args.project, init=False)
            configuration_path = find_configuration_file(
                Path.cwd(), args.working_dir, args.configuration_file
            )
            profile = load_profile(Path.cwd(), args.profile)
            backends = profile.backends
            if args.backends:
                backends = args.backends
            run_plan = api.runs.get_plan(
                configuration_path=configuration_path,
                backends=backends,
                resources=profile.resources,  # pass profile piece by piece
                spot_policy=profile.spot_policy,
                retry_policy=profile.retry_policy,
                max_duration=profile.max_duration,
                max_price=profile.max_price,
                working_dir=args.working_dir,
                run_name=args.run_name,
            )
        except ConfigurationError as e:
            raise CLIError(str(e))

        print_run_plan(run_plan)
        if not args.yes and not Confirm.ask("Continue?"):
            console.print("\nExiting...")
            return

        run_plan.run_spec.run_name = None  # TODO fix server behaviour
        run = api.runs.exec_plan(run_plan, reserve_ports=not args.detach)
        logging.info(run.name)
        if args.detach:
            logging.info("Detaching...")
            return

        stop_at_exit = True
        try:
            # TODO spinner
            if not run.attach():
                logging.info(run.status)
                logging.info("Run is not running")
                stop_at_exit = False
                return
            logging.info(run.ports)
            for entry in run.logs():
                sys.stdout.buffer.write(entry)
                sys.stdout.buffer.flush()

        except KeyboardInterrupt:
            logging.info("Interrupted")  # TODO ask to stop or just detach
        finally:
            run.detach()
            if stop_at_exit:
                logging.info("Stopping...")
                run.stop()
