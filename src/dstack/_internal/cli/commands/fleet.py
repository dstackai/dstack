import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.fleet import print_fleets_table


class FleetCommand(APIBaseCommand):
    NAME = "fleet"
    DESCRIPTION = "Manage fleets"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List fleets", formatter_class=self._parser.formatter_class
        )
        list_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show more information"
        )
        list_parser.set_defaults(subfunc=self._list)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        fleets = self.api.client.fleets.list(self.api.project)
        print_fleets_table(fleets, verbose=getattr(args, "verbose", False))
