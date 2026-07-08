import argparse
import sys
import time
from typing import Iterable

from rich.live import Live

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import (
    EndpointNameCompleter,
    EndpointPresetNameCompleter,
)
from dstack._internal.cli.services.endpoint_logs import EndpointLogPoller
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
    get_start_time,
)
from dstack._internal.cli.utils.endpoint import (
    filter_endpoints_for_listing,
    get_endpoints_table,
    print_endpoint,
    print_endpoints_table,
)
from dstack._internal.cli.utils.preset import print_endpoint_presets_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.endpoints import Endpoint
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
                    "Show all endpoints. By default, it shows unfinished endpoints, "
                    "or the last finished endpoint if there are no unfinished endpoints."
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

        logs_parser = subparsers.add_parser(
            "logs",
            help="Show endpoint logs",
            formatter_class=self._parser.formatter_class,
        )
        logs_parser.add_argument(
            "name",
            help="The name of the endpoint",
        ).completer = EndpointNameCompleter()  # type: ignore[attr-defined]
        logs_parser.add_argument(
            "-w",
            "--watch",
            help="Watch endpoint logs in realtime",
            action="store_true",
        )
        logs_parser.add_argument(
            "--since",
            help=(
                "Show only logs newer than the specified date."
                " Can be a duration (e.g. 10s, 5m, 1d) or an RFC 3339 string (e.g. 2023-09-24T15:30:00Z)."
            ),
            type=str,
        )
        logs_parser.set_defaults(subfunc=self._logs)

        stop_parser = subparsers.add_parser(
            "stop",
            help="Stop an endpoint",
            formatter_class=self._parser.formatter_class,
        )
        stop_parser.add_argument(
            "name",
            help="The name of the endpoint",
        ).completer = EndpointNameCompleter()  # type: ignore[attr-defined]
        stop_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        stop_parser.set_defaults(subfunc=self._stop)

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
            help="Output in JSON format",
        )
        get_parser.set_defaults(subfunc=self._get)

        preset_parser = subparsers.add_parser(
            "preset",
            help="Manage endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        preset_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show more information"
        )
        preset_parser.set_defaults(subfunc=self._preset_list)
        preset_subparsers = preset_parser.add_subparsers(dest="preset_action")

        preset_list_parser = preset_subparsers.add_parser(
            "list",
            help="List endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        preset_list_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show more information",
        )
        preset_list_parser.set_defaults(subfunc=self._preset_list)

        preset_get_parser = preset_subparsers.add_parser(
            "get",
            help="Get an endpoint preset",
            formatter_class=self._parser.formatter_class,
        )
        preset_get_parser.add_argument(
            "model",
            metavar="MODEL",
            help="The model of the endpoint preset",
        ).completer = EndpointPresetNameCompleter()  # type: ignore[attr-defined]
        preset_get_parser.add_argument(
            "--json",
            action="store_true",
            help="Output in JSON format",
        )
        preset_get_parser.set_defaults(subfunc=self._preset_get)

        preset_delete_parser = preset_subparsers.add_parser(
            "delete",
            help="Delete endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        preset_delete_parser.add_argument(
            "model",
            metavar="MODEL",
            help="The model of the endpoint preset",
        ).completer = EndpointPresetNameCompleter()  # type: ignore[attr-defined]
        preset_delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        preset_delete_parser.set_defaults(subfunc=self._preset_delete)

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

    def _logs(self, args: argparse.Namespace):
        try:
            endpoint = self.api.client.endpoints.get(
                project_name=self.api.project,
                name=args.name,
            )
        except ResourceNotExistsError:
            console.print("Endpoint not found")
            exit(1)

        start_time = get_start_time(args.since)
        try:
            for log in self._get_endpoint_logs(
                endpoint=endpoint, start_time=start_time, watch=args.watch
            ):
                sys.stdout.buffer.write(log)
                sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            pass

    def _get_endpoint_logs(
        self, endpoint: Endpoint, start_time, watch: bool = False
    ) -> Iterable[bytes]:
        poller = EndpointLogPoller(api=self.api, endpoint=endpoint, start_time=start_time)
        while True:
            yield from poller.poll()
            if not watch:
                break
            time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)

    def _stop(self, args: argparse.Namespace):
        try:
            endpoint = self.api.client.endpoints.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print(f"Endpoint [code]{args.name}[/] does not exist")
            exit(1)

        if endpoint.status.is_finished():
            console.print(f"Endpoint [code]{args.name}[/] is already {endpoint.status.value}")
            return

        if not args.yes and not confirm_ask(f"Stop the endpoint [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Stopping endpoint..."):
            self.api.client.endpoints.stop(project_name=self.api.project, names=[args.name])

        console.print(f"Endpoint [code]{args.name}[/] stopping")

    def _get(self, args: argparse.Namespace):
        try:
            endpoint = self.api.client.endpoints.get(
                project_name=self.api.project,
                name=args.name,
            )
        except ResourceNotExistsError:
            console.print("Endpoint not found")
            exit(1)

        if args.json:
            print(pydantic_orjson_dumps_with_indent(endpoint.dict(), default=None))
            return
        print_endpoint(endpoint)

    def _preset_list(self, args: argparse.Namespace):
        presets = self.api.client.endpoint_presets.list(self.api.project)
        print_endpoint_presets_table(presets, verbose=args.verbose)

    def _preset_get(self, args: argparse.Namespace):
        if not args.json:
            console.print("Use --json to output the endpoint preset.")
            exit(1)
        try:
            preset = self.api.client.endpoint_presets.get(
                project_name=self.api.project,
                model=args.model,
            )
        except ResourceNotExistsError:
            console.print(f"Endpoint preset for model [code]{args.model}[/] does not exist")
            exit(1)
        print(pydantic_orjson_dumps_with_indent(preset.dict(), default=None))

    def _preset_delete(self, args: argparse.Namespace):
        presets = self.api.client.endpoint_presets.list(self.api.project)
        if args.model not in {preset.model for preset in presets}:
            console.print(f"Endpoint preset for model [code]{args.model}[/] does not exist")
            exit(1)

        if not args.yes and not confirm_ask(
            f"Delete the endpoint preset for model [code]{args.model}[/]?"
        ):
            console.print("\nExiting...")
            return

        try:
            with console.status("Deleting endpoint preset..."):
                self.api.client.endpoint_presets.delete(
                    project_name=self.api.project,
                    models=[args.model],
                )
        except ResourceNotExistsError:
            console.print(f"Endpoint preset for model [code]{args.model}[/] does not exist")
            exit(1)

        console.print(f"Endpoint preset for model [code]{args.model}[/] deleted")
