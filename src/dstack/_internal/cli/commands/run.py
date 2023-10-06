import argparse
import os
import sys
import time
from pathlib import Path

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.run import print_run_plan
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.services.configs.configuration import find_configuration_file
from dstack._internal.core.services.configs.profile import load_profile
from dstack._internal.utils.logging import get_logger
from dstack.api import RunStatus

logger = get_logger(__name__)


class RunCommand(APIBaseCommand):
    NAME = "run"
    DESCRIPTION = "Run .dstack.yml configuration"

    def _register(self):
        super()._register()
        # TODO custom help action
        # self._parser.add_argument("-h", "--help", nargs="?", choices=("task", "dev-environment", "service"))
        self._parser.add_argument("working_dir")
        self._parser.add_argument(
            "-f",
            "--file",
            type=Path,
            metavar="FILE",
            help="The path to the run configuration file. Defaults to [code]WORKING_DIR/.dstack.yml[/].",
            dest="configuration_file",
        )
        self._parser.add_argument(
            "--profile",
            metavar="NAME",
            help="The name of the profile",
            default=os.getenv("DSTACK_PROFILE"),
        )
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
            "-b",
            "--backend",
            action="append",
            metavar="NAME",
            dest="backends",
            help="The backends that will be tried for provisioning",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        try:
            configuration_path = find_configuration_file(
                Path.cwd(), args.working_dir, args.configuration_file
            )
            profile = load_profile(Path.cwd(), args.profile)
            backends = profile.backends
            if args.backends:
                backends = args.backends
            with console.status("Getting run plan..."):
                run_plan = self.api.runs.get_plan(
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
        if not args.yes and not confirm_ask("Continue?"):
            console.print("\nExiting...")
            return

        run_plan.run_spec.run_name = None  # TODO fix server behaviour
        run = self.api.runs.exec_plan(run_plan, reserve_ports=not args.detach)
        if args.detach:
            console.print("Run submitted, detaching...")
            return

        abort_at_exit = True
        try:
            with console.status(f"Launching [code]{run.name}[/]") as status:
                while run.status in (
                    RunStatus.SUBMITTED,
                    RunStatus.PENDING,
                    RunStatus.PROVISIONING,
                ):
                    status.update(
                        f"Launching [code]{run.name}[/] [secondary]({run.status.value})[/]"
                    )
                    time.sleep(5)
                    run.refresh()
            console.print(
                f"[code]{run.name}[/] provisioning completed [secondary]({run.status.value})[/]"
            )

            if run.attach():
                for entry in run.logs():
                    console.print(entry.decode("utf-8"), markup=False, highlight=False, end="")
            else:
                console.print("[error]Failed to attach, exiting...[/]")

            run.refresh()
            if run.status.is_finished():
                abort_at_exit = False
        except KeyboardInterrupt:
            try:
                if not confirm_ask("\nStop the run before detaching?"):
                    console.print("Detached")
                    abort_at_exit = False
                    return
                # Gently stop the run and wait for it to finish
                with console.status("Stopping..."):
                    run.stop(abort=False)
                    while not run.status.is_finished():
                        time.sleep(2)
                        run.refresh()
                console.print("Stopped")
                abort_at_exit = False
            except KeyboardInterrupt:
                abort_at_exit = True
        finally:
            run.detach()
            if abort_at_exit:
                with console.status("Aborting..."):
                    run.stop(abort=True)
                console.print("Aborted")
