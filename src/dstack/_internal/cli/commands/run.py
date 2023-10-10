import argparse
import sys
import time
from pathlib import Path

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.profile import (
    apply_profile_args,
    register_profile_args,
)
from dstack._internal.cli.services.configurators.run import (
    BaseRunConfigurator,
    run_configurators_mapping,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.run import print_run_plan
from dstack._internal.core.errors import CLIError, ConfigurationError, ResourceExistsError
from dstack._internal.core.models.configurations import ConfigurationType
from dstack._internal.utils.logging import get_logger
from dstack.api import RunStatus
from dstack.api.utils import load_configuration, load_profile

logger = get_logger(__name__)
NOTSET = object()


class RunCommand(APIBaseCommand):
    NAME = "run"
    DESCRIPTION = "Run .dstack.yml configuration"
    DEFAULT_HELP = False

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-h",
            "--help",
            nargs="?",
            type=ConfigurationType,
            default=NOTSET,
            help="Show this help message and exit. TYPE is one of [code]task[/], [code]dev-environment[/], [code]service[/]",
            dest="help",
            metavar="TYPE",
        )
        self._parser.add_argument("working_dir")
        self._parser.add_argument(
            "-f",
            "--file",
            type=Path,
            metavar="FILE",
            help="The path to the run configuration file. Defaults to [code]WORKING_DIR/.dstack.yml[/]",
            dest="configuration_file",
        )
        self._parser.add_argument(
            "-n",
            "--name",
            dest="run_name",
            help="The name of the run. If not specified, a random name is assigned",
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
        register_profile_args(self._parser)

    def _command(self, args: argparse.Namespace):
        if args.help is not NOTSET:
            if args.help is not None:
                run_configurators_mapping[ConfigurationType(args.help)].register(self._parser)
            else:
                BaseRunConfigurator.register(self._parser)
            self._parser.print_help()
            return

        super()._command(args)
        try:
            profile = load_profile(Path.cwd(), args.profile)
            apply_profile_args(args, profile)

            configuration_path, conf = load_configuration(
                Path.cwd(), args.working_dir, args.configuration_file
            )
            logger.debug("Configuration loaded: %s", configuration_path)
            parser = argparse.ArgumentParser()
            configurator = run_configurators_mapping[ConfigurationType(conf.type)]
            configurator.register(parser)
            configurator.apply(parser.parse_args(args.unknown), conf)

            with console.status("Getting run plan..."):
                run_plan = self.api.runs.get_plan(
                    configuration=conf,
                    configuration_path=configuration_path,
                    backends=profile.backends,
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

        try:
            with console.status("Submitting run..."):
                run = self.api.runs.exec_plan(run_plan, reserve_ports=not args.detach)
        except ResourceExistsError as e:
            raise CLIError(e.msg)

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
                    sys.stdout.buffer.write(entry)
                    sys.stdout.buffer.flush()
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
