import argparse
import time

from rich.live import Live

import dstack._internal.cli.utils.run as run_utils
from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    console,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


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
        self._parser.add_argument(
            "-n",
            "--last",
            help="Show only the last N runs. Implies --all",
            type=int,
            default=None,
        )
        self._parser.add_argument(
            "--format",
            choices=["plain", "json"],
            default="plain",
            help="Output format (default: plain)",
        )
        self._parser.add_argument(
            "--json",
            action="store_const",
            const="json",
            dest="format",
            help="Output in JSON format (equivalent to --format json)",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        if args.watch and args.format == "json":
            raise CLIError("JSON output is not supported together with --watch")

        runs = self.api.runs.list(all=args.all, limit=args.last)
        deprecated_router_runs = [
            run._run.run_spec.run_name
            for run in runs
            if not run.status.is_finished()
            and isinstance(run._run.run_spec.configuration, ServiceConfiguration)
            and run._run.run_spec.configuration.router is not None
            and run._run.run_spec.run_name is not None
        ]
        if deprecated_router_runs and args.format != "json":
            logger.warning(
                "Specifying `router` in service configurations is deprecated"
                " and will be disallowed in a future release."
                " Please migrate to replica-based routers:"
                " https://dstack.ai/docs/concepts/services/#pd-disaggregation"
                " (affected runs: %s)",
                ", ".join(deprecated_router_runs),
            )
        if not args.watch:
            if args.format == "json":
                run_utils.print_runs_json(self.api.project, runs)
            else:
                console.print(run_utils.get_runs_table(runs, verbose=args.verbose))
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(run_utils.get_runs_table(runs, verbose=args.verbose))
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    runs = self.api.runs.list(all=args.all, limit=args.last)
        except KeyboardInterrupt:
            pass
