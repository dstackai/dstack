import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import EndpointPresetNameCompleter
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.preset import print_endpoint_presets_table
from dstack._internal.core.errors import ResourceNotExistsError


class PresetCommand(APIBaseCommand):
    NAME = "preset"
    DESCRIPTION = "Manage endpoint presets"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List endpoint presets", formatter_class=self._parser.formatter_class
        )
        list_parser.set_defaults(subfunc=self._list)

        delete_parser = subparsers.add_parser(
            "delete",
            help="Delete endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        delete_parser.add_argument(
            "name",
            help="The name of the endpoint preset",
        ).completer = EndpointPresetNameCompleter()  # type: ignore[attr-defined]
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        presets = self.api.client.endpoint_presets.list(self.api.project)
        print_endpoint_presets_table(presets)

    def _delete(self, args: argparse.Namespace):
        presets = self.api.client.endpoint_presets.list(self.api.project)
        if args.name not in {preset.name for preset in presets}:
            console.print(f"Endpoint preset [code]{args.name}[/] does not exist")
            exit(1)

        if not args.yes and not confirm_ask(f"Delete the endpoint preset [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        try:
            with console.status("Deleting endpoint preset..."):
                self.api.client.endpoint_presets.delete(
                    project_name=self.api.project,
                    names=[args.name],
                )
        except ResourceNotExistsError:
            console.print(f"Endpoint preset [code]{args.name}[/] does not exist")
            exit(1)

        console.print(f"Endpoint preset [code]{args.name}[/] deleted")
