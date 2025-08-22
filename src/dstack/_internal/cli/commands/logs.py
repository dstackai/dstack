import argparse
import sys

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import RunNameCompleter
from dstack._internal.core.errors import CLIError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class LogsCommand(APIBaseCommand):
    NAME = "logs"
    DESCRIPTION = "Show logs"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-d", "--diagnose", action="store_true", help="Show run diagnostic logs"
        )
        self._parser.add_argument(
            "--replica",
            help="The replica number. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument(
            "--job",
            help="The job number inside the replica. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument("run_name").completer = RunNameCompleter(all=True)  # type: ignore[attr-defined]

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        run = self.api.runs.get(args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        logs = run.logs(
            diagnose=args.diagnose,
            replica_num=args.replica,
            job_num=args.job,
        )
        try:
            for log in logs:
                sys.stdout.buffer.write(log)
                sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            pass
