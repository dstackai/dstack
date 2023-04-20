import os
import time
from argparse import Namespace

from rich.live import Live

from dstack.api.backend import list_backends
from dstack.api.run import list_runs_with_merged_backends
from dstack.cli.commands import BasicCommand
from dstack.cli.common import (
    check_backend,
    check_config,
    check_git,
    check_init,
    generate_runs_table,
    print_runs,
)
from dstack.cli.config import config
from dstack.core.repo import RemoteRepo

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

    @check_config
    @check_git
    @check_backend
    @check_init
    def _command(self, args: Namespace):
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        backends = list_backends(repo)
        list_runs = list_runs_with_merged_backends(backends, args.run_name, args.all)
        if args.watch:
            try:
                with Live(
                    generate_runs_table(list_runs, verbose=args.verbose),
                    refresh_per_second=REFRESH_RATE_PER_SEC,
                ) as live:
                    while True:
                        time.sleep(LIVE_PROVISION_INTERVAL_SECS)
                        list_runs = list_runs_with_merged_backends(
                            backends, args.run_name, args.all
                        )
                        live.update(generate_runs_table(list_runs, verbose=args.verbose))
            except KeyboardInterrupt:
                pass
        else:
            print_runs(list_runs, verbose=args.verbose)
