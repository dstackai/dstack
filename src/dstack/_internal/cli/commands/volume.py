import argparse
import time

from rich.live import Live

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import VolumeNameCompleter
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.volume import get_volumes_table, print_volumes_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


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
        list_parser.set_defaults(subfunc=self._list)

        for parser in [self._parser, list_parser]:
            parser.add_argument(
                "-w",
                "--watch",
                help="Update listing in realtime",
                action="store_true",
            )
            parser.add_argument(
                "-v", "--verbose", action="store_true", help="Show more information"
            )

        delete_parser = subparsers.add_parser(
            "delete",
            help="Delete volumes",
            formatter_class=self._parser.formatter_class,
        )
        delete_parser.add_argument(
            "name",
            help="The name of the volume",
        ).completer = VolumeNameCompleter()  # type: ignore[attr-defined]
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

        get_parser = subparsers.add_parser(
            "get", help="Get a volume", formatter_class=self._parser.formatter_class
        )
        get_parser.add_argument(
            "name",
            metavar="NAME",
            help="The name of the volume",
        ).completer = VolumeNameCompleter()  # type: ignore[attr-defined]
        get_parser.add_argument(
            "--json",
            action="store_true",
            required=True,
            help="Output in JSON format",
        )
        get_parser.set_defaults(subfunc=self._get)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        volumes = self.api.client.volumes.list(self.api.project)
        if not args.watch:
            print_volumes_table(volumes, verbose=args.verbose)
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_volumes_table(volumes, verbose=args.verbose))
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    volumes = self.api.client.volumes.list(self.api.project)
        except KeyboardInterrupt:
            pass

    def _delete(self, args: argparse.Namespace):
        try:
            self.api.client.volumes.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print(f"Volume [code]{args.name}[/] does not exist")
            exit(1)

        if not args.yes and not confirm_ask(f"Delete the volume [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting volume..."):
            self.api.client.volumes.delete(project_name=self.api.project, names=[args.name])

        console.print(f"Volume [code]{args.name}[/] deleted")

    def _get(self, args: argparse.Namespace):
        # TODO: Implement non-json output format
        try:
            volume = self.api.client.volumes.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print("Volume not found")
            exit(1)

        print(pydantic_orjson_dumps_with_indent(volume.dict(), default=None))
