import argparse

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.imports import Import


class ImportCommand(APIBaseCommand):
    NAME = "import"
    DESCRIPTION = "Manage imports"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List imports", formatter_class=self._parser.formatter_class
        )
        list_parser.set_defaults(subfunc=self._list)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        imports = self.api.client.imports.list(self.api.project)
        print_imports_table(imports)


def print_imports_table(imports: list[Import]):
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("FLEETS")

    for imp in imports:
        name = f"{imp.export.project_name}/{imp.export.name}"
        fleets = (
            ", ".join([f.name for f in imp.export.exported_fleets])
            if imp.export.exported_fleets
            else "-"
        )

        row = {
            "NAME": name,
            "FLEETS": fleets,
        }
        add_row_from_dict(table, row)

    console.print(table)
    console.print()
