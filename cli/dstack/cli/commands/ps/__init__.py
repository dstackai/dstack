import time
from argparse import Namespace

from rich.live import Live

from dstack.api.backend import list_backends
from dstack.api.run import list_runs_with_merged_backends
from dstack.cli.commands import BasicCommand
from dstack.cli.common import generate_runs_table, print_runs
from dstack.core.error import check_config, check_git

LIVE_PROVISION_INTERVAL_SECS = 2

REFRESH_RATE_PER_SEC = 3


class PSCommand(BasicCommand):
    NAME = "ps"
    DESCRIPTION = "List runs"

    def __init__(self, parser):
        super(PSCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name", metavar="RUN", type=str, nargs="?", help="A name of a run"
        )
        self._parser.add_argument(
            "-a",
            "--all",
            help="Show all runs. "
            "By default, it only shows unfinished runs or the last finished.",
            action="store_true",
        )
        self._parser.add_argument(
            "-w",
            "--watch",
            help="Watch statuses of runs in realtime",
            action="store_true",
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        list_runs = list_runs_with_merged_backends(list_backends(), args.run_name, args.all)
        if args.watch:
            try:
                with Live(
                    generate_runs_table(list_runs), refresh_per_second=REFRESH_RATE_PER_SEC
                ) as live:
                    while True:
                        time.sleep(LIVE_PROVISION_INTERVAL_SECS)
                        list_runs = list_runs_with_merged_backends(
                            list_backends(), args.run_name, args.all
                        )
                        live.update(generate_runs_table(list_runs))
            except KeyboardInterrupt:
                pass
        else:
            print_runs(list_runs)
