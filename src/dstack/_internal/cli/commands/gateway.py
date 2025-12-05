import argparse
import time

from rich.live import Live

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import GatewayNameCompleter
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.gateway import (
    get_gateways_table,
    print_gateways_json,
    print_gateways_table,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class GatewayCommand(APIBaseCommand):
    NAME = "gateway"
    DESCRIPTION = "Manage gateways"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List gateways", formatter_class=self._parser.formatter_class
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
            parser.add_argument(
                "--format",
                choices=["plain", "json"],
                default="plain",
                help="Output format (default: plain)",
            )
            parser.add_argument(
                "--json",
                action="store_const",
                const="json",
                dest="format",
                help="Output in JSON format (equivalent to --format json)",
            )

        delete_parser = subparsers.add_parser(
            "delete", help="Delete a gateway", formatter_class=self._parser.formatter_class
        )
        delete_parser.set_defaults(subfunc=self._delete)
        delete_parser.add_argument(
            "name", help="The name of the gateway"
        ).completer = GatewayNameCompleter()  # type: ignore[attr-defined]
        delete_parser.add_argument(
            "-y", "--yes", action="store_true", help="Don't ask for confirmation"
        )

        update_parser = subparsers.add_parser(
            "update", help="Update a gateway", formatter_class=self._parser.formatter_class
        )
        update_parser.set_defaults(subfunc=self._update)
        update_parser.add_argument(
            "name", help="The name of the gateway"
        ).completer = GatewayNameCompleter()  # type: ignore[attr-defined]
        update_parser.add_argument(
            "--set-default", action="store_true", help="Set it the default gateway for the project"
        )
        update_parser.add_argument("--domain", help="Set the domain for the gateway")

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        # TODO handle errors
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        if args.watch and args.format == "json":
            raise CLIError("JSON output is not supported together with --watch")

        gateways = self.api.client.gateways.list(self.api.project)
        if not args.watch:
            if args.format == "json":
                print_gateways_json(gateways, project=self.api.project)
            else:
                print_gateways_table(gateways, verbose=args.verbose)
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_gateways_table(gateways, verbose=args.verbose))
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    gateways = self.api.client.gateways.list(self.api.project)
        except KeyboardInterrupt:
            pass

    def _delete(self, args: argparse.Namespace):
        gateway = self.api.client.gateways.get(self.api.project, args.name)
        print_gateways_table([gateway])
        if args.yes or confirm_ask("Do you want to delete the gateway?"):
            with console.status("Deleting gateway..."):
                self.api.client.gateways.delete(self.api.project, [args.name])
            console.print("Gateway deleted")
        else:
            console.print("Exiting...")
            return

    def _update(self, args: argparse.Namespace):
        with console.status("Updating gateway..."):
            if args.set_default:
                self.api.client.gateways.set_default(self.api.project, args.name)
            if args.domain:
                self.api.client.gateways.set_wildcard_domain(
                    self.api.project, args.name, args.domain
                )
        gateway = self.api.client.gateways.get(self.api.project, args.name)
        print_gateways_table([gateway])
