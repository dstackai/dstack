import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.volume import print_volumes_table


class VolumeCommand(APIBaseCommand):
    NAME = "volume"
    DESCRIPTION = "Manage volumes"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List volumes", formatter_class=self._parser.formatter_class
        )
        list_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show more information"
        )
        list_parser.set_defaults(subfunc=self._list)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        volumes = self.api.client.volumes.list(self.api.project)
        print_volumes_table(volumes, verbose=getattr(args, "verbose", False))
