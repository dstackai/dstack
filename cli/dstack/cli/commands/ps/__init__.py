from argparse import Namespace

from dstack.cli.commands import BasicCommand
from dstack.cli.common import print_runs
from dstack.core.error import check_config, check_git
from dstack.api.run import list_runs_with_merged_backends
from dstack.api.backend import list_backends


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
            help="Show status for all runs. "
            "By default, it shows only status for unfinished runs, or the last finished.",
            action="store_true",
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        print_runs(list_runs_with_merged_backends(list_backends(), args.run_name, args.all))
