import argparse
from typing import Any, Union

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import ExportNameCompleter
from dstack._internal.cli.utils.common import add_row_from_dict, confirm_ask, console
from dstack._internal.core.models.exports import Export


class ExportCommand(APIBaseCommand):
    NAME = "export"
    DESCRIPTION = "Manage exports"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List exports", formatter_class=self._parser.formatter_class
        )
        list_parser.set_defaults(subfunc=self._list)

        create_parser = subparsers.add_parser(
            "create", help="Create an export", formatter_class=self._parser.formatter_class
        )
        create_parser.add_argument(
            "name",
            help="The name of the export",
        )
        create_parser.add_argument(
            "--importer",
            action="append",
            dest="importers",
            help="Importer project name (can be specified multiple times)",
            default=[],
        )
        create_parser.add_argument(
            "--fleet",
            action="append",
            dest="fleets",
            help="Fleet name to export (can be specified multiple times)",
            default=[],
        )
        create_parser.set_defaults(subfunc=self._create)

        update_parser = subparsers.add_parser(
            "update", help="Update an export", formatter_class=self._parser.formatter_class
        )
        update_parser.add_argument(
            "name",
            help="The name of the export",
        ).completer = ExportNameCompleter()  # type: ignore[attr-defined]
        update_parser.add_argument(
            "--add-importer",
            action="append",
            dest="add_importers",
            help="Importer project name to add (can be specified multiple times)",
            default=[],
        )
        update_parser.add_argument(
            "--remove-importer",
            action="append",
            dest="remove_importers",
            help="Importer project name to remove (can be specified multiple times)",
            default=[],
        )
        update_parser.add_argument(
            "--add-fleet",
            action="append",
            dest="add_fleets",
            help="Fleet name to add (can be specified multiple times)",
            default=[],
        )
        update_parser.add_argument(
            "--remove-fleet",
            action="append",
            dest="remove_fleets",
            help="Fleet name to remove (can be specified multiple times)",
            default=[],
        )
        update_parser.set_defaults(subfunc=self._update)

        delete_parser = subparsers.add_parser(
            "delete", help="Delete an export", formatter_class=self._parser.formatter_class
        )
        delete_parser.add_argument(
            "name",
            help="The name of the export",
        ).completer = ExportNameCompleter()  # type: ignore[attr-defined]
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        exports = self.api.client.exports.list(self.api.project)
        print_exports_table(exports)

    def _create(self, args: argparse.Namespace):
        with console.status("Creating export..."):
            export = self.api.client.exports.create(
                project_name=self.api.project,
                name=args.name,
                importer_projects=args.importers,
                exported_fleets=args.fleets,
            )
        print_exports_table([export])

    def _update(self, args: argparse.Namespace):
        with console.status("Updating export..."):
            export = self.api.client.exports.update(
                project_name=self.api.project,
                name=args.name,
                add_importer_projects=args.add_importers,
                remove_importer_projects=args.remove_importers,
                add_exported_fleets=args.add_fleets,
                remove_exported_fleets=args.remove_fleets,
            )
        print_exports_table([export])

    def _delete(self, args: argparse.Namespace):
        if not args.yes and not confirm_ask(f"Delete the export [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting export..."):
            self.api.client.exports.delete(project_name=self.api.project, name=args.name)

        console.print(f"Export [code]{args.name}[/] deleted")


def print_exports_table(exports: list[Export]):
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("FLEETS")
    table.add_column("IMPORTERS")

    for export in exports:
        fleets = (
            ", ".join([f.name for f in export.exported_fleets]) if export.exported_fleets else "-"
        )
        importers = ", ".join([i.project_name for i in export.imports]) if export.imports else "-"

        row: dict[Union[str, int], Any] = {
            "NAME": export.name,
            "FLEETS": fleets,
            "IMPORTERS": importers,
        }
        add_row_from_dict(table, row)

    console.print(table)
    console.print()
