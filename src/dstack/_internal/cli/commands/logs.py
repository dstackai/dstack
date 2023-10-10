import argparse
import sys

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import confirm_ask
from dstack._internal.core.errors import CLIError


class LogsCommand(APIBaseCommand):
    NAME = "logs"
    DESCRIPTION = "Show run logs"

    def _register(self):
        super()._register()
        self._parser.add_argument("-d", "--diagnose", action="store_true")
        self._parser.add_argument("run_name")

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        run = self.api.runs.get(args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        logs = run.logs(diagnose=args.diagnose)
        for log in logs:
            sys.stdout.buffer.write(log)
        sys.stdout.buffer.flush()
