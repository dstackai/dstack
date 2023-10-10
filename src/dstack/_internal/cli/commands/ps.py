import argparse
import time

from rich.live import Live

import dstack._internal.cli.utils.run as run_utils
from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import console

REFRESH_RATE_PER_SEC = 3
LIVE_PROVISION_INTERVAL_SECS = 2


class PsCommand(APIBaseCommand):
    NAME = "ps"
    DESCRIPTION = "List runs"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-a",
            "--all",
            help="Show all runs. By default, it only shows unfinished runs or the last finished.",
            action="store_true",
        )
        self._parser.add_argument(
            "-v",
            "--verbose",
            help="Show more information about runs",
            action="store_true",
        )
        self._parser.add_argument(
            "-w",
            "--watch",
            help="Watch statuses of runs in realtime",
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        runs = self.api.runs.list(all=args.all)
        if not args.watch:
            console.print(run_utils.generate_runs_table(runs, verbose=args.verbose))
            return

        try:
            with Live(console=console, refresh_per_second=REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(run_utils.generate_runs_table(runs, verbose=args.verbose))
                    time.sleep(LIVE_PROVISION_INTERVAL_SECS)
                    runs = self.api.runs.list(all=args.all)
        except KeyboardInterrupt:
            pass
