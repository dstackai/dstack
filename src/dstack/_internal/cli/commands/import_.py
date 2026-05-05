import argparse

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import ImportNameCompleter
from dstack._internal.cli.utils.common import add_row_from_dict, confirm_ask, console
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

        delete_parser = subparsers.add_parser(
            "delete", help="Delete an import", formatter_class=self._parser.formatter_class
        )
        delete_parser.add_argument(
            "name",
            help="The import to delete, in `export-project/export-name` format",
        ).completer = ImportNameCompleter()  # type: ignore[attr-defined]
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        imports = self.api.client.imports.list(self.api.project)
        print_imports_table(imports)

    def _delete(self, args: argparse.Namespace):
        parts = args.name.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            self._parser.error(
                f"Invalid format: {args.name!r}. Expected <export-project>/<export-name>"
            )
        export_project_name, export_name = parts

        if not args.yes and not confirm_ask(f"Delete the import [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting import..."):
            self.api.client.imports.delete(
                project_name=self.api.project,
                export_project_name=export_project_name,
                export_name=export_name,
            )

        console.print(f"Import [code]{args.name}[/] deleted")


def print_imports_table(imports: list[Import]):
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("FLEETS")
    table.add_column("GATEWAYS")

    for imp in imports:
        name = f"{imp.export.project_name}/{imp.export.name}"
        fleets = (
            ", ".join([f.name for f in imp.export.exported_fleets])
            if imp.export.exported_fleets
            else "-"
        )
        gateways = (
            ", ".join([g.name for g in imp.export.exported_gateways])
            if imp.export.exported_gateways
            else "-"
        )

        row = {
            "NAME": name,
            "FLEETS": fleets,
            "GATEWAYS": gateways,
        }
        add_row_from_dict(table, row)

    console.print(table)
    console.print()
