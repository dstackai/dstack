import argparse

import dstack._internal.cli.utils.run as run_utils
from dstack._internal.cli.commands import APIBaseCommand


class PsCommand(APIBaseCommand):
    NAME = "ps"
    DESCRIPTION = "List runs"

    def _register(self):
        super()._register()
        # TODO only active runs
        # TODO verbose
        # TODO print all submissions
        # TODO limit

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        runs = self.api.runs.list()
        run_utils.print_runs_table(runs)
