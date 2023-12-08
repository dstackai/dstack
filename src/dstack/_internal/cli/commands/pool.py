import argparse
from typing import List

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import console
from dstack._internal.utils.common import pretty_date


def print_pool_table(pools: List, verbose):
    table = Table(box=None)
    table.add_column("NAME")
    table.add_column("DEFAULT")
    if verbose:
        table.add_column("CREATED")

    for pool in pools:
        row = [pool.name, "default" if pool.default else ""]
        if verbose:
            row.append(pretty_date(pool.created_at))
        table.add_row(*row)

    console.print(table)
    console.print()


class PoolCommand(APIBaseCommand):
    NAME = "pool"
    DESCRIPTION = "Pool management"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List pools", formatter_class=self._parser.formatter_class
        )
        list_parser.add_argument("-v", "--verbose", help="Show more information")
        list_parser.set_defaults(subfunc=self._list)

        create_parser = subparsers.add_parser(
            "create", help="Create pool", formatter_class=self._parser.formatter_class
        )
        create_parser.add_argument("-n", "--name", dest="pool_name", help="The name of the pool")
        create_parser.set_defaults(subfunc=self._create)

        delete_parser = subparsers.add_parser(
            "delete", help="Delete pool", formatter_class=self._parser.formatter_class
        )
        delete_parser.add_argument(
            "-n", "--name", dest="pool_name", help="The name of the pool", required=True
        )
        delete_parser.set_defaults(subfunc=self._delete)

        show_parser = subparsers.add_parser(
            "show", help="Show pool's instances", formatter_class=self._parser.formatter_class
        )
        show_parser.add_argument(
            "-n", "--name", dest="pool_name", help="The name of the pool", required=True
        )
        show_parser.set_defaults(subfunc=self._show)

    def _list(self, args: argparse.Namespace):
        pools = self.api.client.pool.list(self.api.project)
        print_pool_table(pools, verbose=getattr(args, "verbose", False))

    def _create(self, args: argparse.Namespace):
        self.api.client.pool.create(self.api.project, args.pool_name)

    def _delete(self, args: argparse.Namespace):
        self.api.client.pool.delete(self.api.project, args.pool_name)

    def _show(self, args: argparse.Namespace):
        self.api.client.pool.show(self.api.project, args.pool_name)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        # TODO handle 404 and other errors
        args.subfunc(args)
