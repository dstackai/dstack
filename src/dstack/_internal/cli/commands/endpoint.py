import argparse
import time

from rich.live import Live

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import EndpointNameCompleter
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.endpoint import (
    filter_endpoints_for_listing,
    get_endpoints_table,
    print_endpoints_table,
)
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


class EndpointCommand(APIBaseCommand):
    NAME = "endpoint"
    DESCRIPTION = "Manage endpoints"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List endpoints", formatter_class=self._parser.formatter_class
        )
        list_parser.set_defaults(subfunc=self._list)

        for parser in [self._parser, list_parser]:
            parser.add_argument(
                "-a",
                "--all",
                help=(
                    "Show all endpoints. By default, it only shows unfinished endpoints "
                    "and the last finished endpoint."
                ),
                action="store_true",
            )
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
                "-n",
                "--last",
                help="Show only the last N endpoints. Implies --all",
                type=int,
                default=None,
            )

        delete_parser = subparsers.add_parser(
            "delete",
            help="Delete endpoints",
            formatter_class=self._parser.formatter_class,
        )
        delete_parser.add_argument(
            "name",
            help="The name of the endpoint",
        ).completer = EndpointNameCompleter()  # type: ignore[attr-defined]
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

        get_parser = subparsers.add_parser(
            "get", help="Get an endpoint", formatter_class=self._parser.formatter_class
        )
        get_parser.add_argument(
            "name",
            metavar="NAME",
            help="The name of the endpoint",
        ).completer = EndpointNameCompleter()  # type: ignore[attr-defined]
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
        endpoints = self._get_endpoints_for_listing(args)
        if not args.watch:
            print_endpoints_table(endpoints, verbose=args.verbose)
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_endpoints_table(endpoints, verbose=args.verbose))
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    endpoints = self._get_endpoints_for_listing(args)
        except KeyboardInterrupt:
            pass

    def _get_endpoints_for_listing(self, args: argparse.Namespace):
        endpoints = self.api.client.endpoints.list(self.api.project)
        return filter_endpoints_for_listing(
            endpoints,
            show_all=args.all,
            limit=args.last,
        )

    def _delete(self, args: argparse.Namespace):
        try:
            self.api.client.endpoints.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print(f"Endpoint [code]{args.name}[/] does not exist")
            exit(1)

        if not args.yes and not confirm_ask(f"Delete the endpoint [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting endpoint..."):
            self.api.client.endpoints.delete(project_name=self.api.project, names=[args.name])

        console.print(f"Endpoint [code]{args.name}[/] deleted")

    def _get(self, args: argparse.Namespace):
        try:
            endpoint = self.api.client.endpoints.get(
                project_name=self.api.project,
                name=args.name,
            )
        except ResourceNotExistsError:
            console.print("Endpoint not found")
            exit(1)

        print(pydantic_orjson_dumps_with_indent(endpoint.dict(), default=None))
