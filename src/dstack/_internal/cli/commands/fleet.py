import argparse
import time

from rich.live import Live

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import FleetNameCompleter
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.fleet import get_fleets_table, print_fleets_table
from dstack._internal.core.errors import ResourceNotExistsError


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
            help="Delete fleets and instances",
            formatter_class=self._parser.formatter_class,
        )
        delete_parser.add_argument(
            "name",
            help="The name of the fleet",
        ).completer = FleetNameCompleter()
        delete_parser.add_argument(
            "-i",
            "--instance",
            action="append",
            metavar="INSTANCE_NUM",
            dest="instances",
            help="The instances to delete",
            type=int,
        )
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        fleets = self.api.client.fleets.list(self.api.project)
        if not args.watch:
            print_fleets_table(fleets, verbose=args.verbose)
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_fleets_table(fleets, verbose=args.verbose))
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    fleets = self.api.client.fleets.list(self.api.project)
        except KeyboardInterrupt:
            pass

    def _delete(self, args: argparse.Namespace):
        try:
            self.api.client.fleets.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print(f"Fleet [code]{args.name}[/] does not exist")
            exit(1)

        if not args.instances:
            if not args.yes and not confirm_ask(f"Delete the fleet [code]{args.name}[/]?"):
                console.print("\nExiting...")
                return

            with console.status("Deleting fleet..."):
                self.api.client.fleets.delete(project_name=self.api.project, names=[args.name])

            console.print(f"Fleet [code]{args.name}[/] deleted")
            return

        if not args.yes and not confirm_ask(
            f"Delete the fleet [code]{args.name}[/] instances [code]{args.instances}[/]?"
        ):
            console.print("\nExiting...")
            return

        with console.status("Deleting fleet instances..."):
            self.api.client.fleets.delete_instances(
                project_name=self.api.project, name=args.name, instance_nums=args.instances
            )

        console.print(f"Fleet [code]{args.name}[/] instances deleted")
