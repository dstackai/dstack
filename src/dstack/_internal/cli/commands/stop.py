import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import RunNameCompleter
from dstack._internal.cli.utils.common import confirm_ask
from dstack._internal.core.errors import CLIError


class StopCommand(APIBaseCommand):
    NAME = "stop"
    DESCRIPTION = "Stop a run"

    def _register(self):
        super()._register()
        self._parser.add_argument("-x", "--abort", action="store_true")
        self._parser.add_argument("-y", "--yes", action="store_true")
        self._parser.add_argument("run_name").completer = RunNameCompleter()

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        run = self.api.runs.get(args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        if args.yes or confirm_ask("Are you sure you want to stop the run?"):
            run.stop(abort=args.abort)
            print("Aborted" if args.abort else "Stopped")
