import time
from argparse import Namespace

from rich.live import Live

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import (
    add_project_argument,
    check_init,
    generate_runs_table,
    print_runs,
)
from dstack._internal.cli.config import get_hub_client

LIVE_PROVISION_INTERVAL_SECS = 2

REFRESH_RATE_PER_SEC = 3


class PSCommand(BasicCommand):
    NAME = "ps"
    DESCRIPTION = "List runs"

    def __init__(self, parser):
        super(PSCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name", metavar="RUN", type=str, nargs="?", help="The name of the run"
        )
        add_project_argument(self._parser)
        self._parser.add_argument(
            "-a",
            "--all",
            help="Show all runs. "
            "By default, it only shows unfinished runs or the last finished.",
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

    @check_init
    def _command(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        runs = list_runs_hub(hub_client, run_name=args.run_name, all=args.all)
        if args.watch:
            try:
                with Live(
                    generate_runs_table(runs, include_configuration=True, verbose=args.verbose),
                    refresh_per_second=REFRESH_RATE_PER_SEC,
                ) as live:
                    while True:
                        time.sleep(LIVE_PROVISION_INTERVAL_SECS)
                        runs = list_runs_hub(hub_client, run_name=args.run_name, all=args.all)
                        live.update(
                            generate_runs_table(
                                runs, include_configuration=True, verbose=args.verbose
                            )
                        )
            except KeyboardInterrupt:
                pass
        else:
            print_runs(runs, include_configuration=True, verbose=args.verbose)
