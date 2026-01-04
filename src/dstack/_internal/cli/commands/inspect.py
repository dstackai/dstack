import argparse
from typing import Union
from uuid import UUID

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import (
    FleetNameCompleter,
    GatewayNameCompleter,
    RunNameCompleter,
    VolumeNameCompleter,
)
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError, ResourceNotExistsError
from dstack._internal.core.models.fleets import Fleet
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.core.models.runs import Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


class InspectCommand(APIBaseCommand):
    NAME = "inspect"
    DESCRIPTION = "Inspect objects (runs, fleets, volumes, gateways)"
    ACCEPT_EXTRA_ARGS = True

    def _normalize_default_subcommand(self) -> None:
        """
        Normalize inspect command args to support default 'run' subcommand.

        This allows users to run:
        - `dstack inspect NAME` instead of `dstack inspect run NAME`
        - `dstack inspect --id UUID` instead of `dstack inspect run --id UUID`

        Since argparse subparsers don't support optional subcommands natively,
        we need to manipulate sys.argv before parsing to insert "run" as the
        default subcommand when the first argument is not a valid subcommand.
        """
        import sys

        if len(sys.argv) > 1 and sys.argv[1] == "inspect" and len(sys.argv) > 2:
            arg = sys.argv[2]
            valid_subcommands = {"run", "fleet", "volume", "gateway"}
            if arg not in valid_subcommands and not arg.startswith("-"):
                sys.argv.insert(2, "run")
            elif arg == "--id":
                sys.argv.insert(2, "run")

    def _register(self) -> None:
        self._normalize_default_subcommand()
        super()._register()
        subparsers = self._parser.add_subparsers(
            dest="subcommand", help="Object type to inspect", metavar="TYPE"
        )

        run_parser = subparsers.add_parser(
            "run", help="Inspect a run", formatter_class=self._parser.formatter_class
        )
        run_parser.add_argument(
            "name",
            nargs="?",
            help="The name of the run",
        ).completer = RunNameCompleter()  # type: ignore[attr-defined]
        run_parser.add_argument(
            "--id",
            type=str,
            help="The ID of the run (UUID)",
        )
        run_parser.set_defaults(subfunc=self._inspect_run)

        fleet_parser = subparsers.add_parser(
            "fleet", help="Inspect a fleet", formatter_class=self._parser.formatter_class
        )
        fleet_parser.add_argument(
            "name",
            nargs="?",
            help="The name of the fleet",
        ).completer = FleetNameCompleter()  # type: ignore[attr-defined]
        fleet_parser.add_argument(
            "--id",
            type=str,
            help="The ID of the fleet (UUID)",
        )
        fleet_parser.set_defaults(subfunc=self._inspect_fleet)

        volume_parser = subparsers.add_parser(
            "volume", help="Inspect a volume", formatter_class=self._parser.formatter_class
        )
        volume_parser.add_argument(
            "name",
            nargs="?",
            help="The name of the volume",
        ).completer = VolumeNameCompleter()  # type: ignore[attr-defined]
        volume_parser.set_defaults(subfunc=self._inspect_volume)

        gateway_parser = subparsers.add_parser(
            "gateway", help="Inspect a gateway", formatter_class=self._parser.formatter_class
        )
        gateway_parser.add_argument(
            "name",
            nargs="?",
            help="The name of the gateway",
        ).completer = GatewayNameCompleter()  # type: ignore[attr-defined]
        gateway_parser.set_defaults(subfunc=self._inspect_gateway)

    def _command(self, args: argparse.Namespace) -> None:
        super()._command(args)
        valid_subcommands = {"run", "fleet", "volume", "gateway"}

        if not hasattr(args, "subcommand") or args.subcommand is None:
            if args.extra_args:
                first_arg = args.extra_args[0]
                if first_arg in valid_subcommands:
                    args.subcommand = first_arg
                    remaining_args = args.extra_args[1:]
                elif first_arg == "--id":
                    args.subcommand = "run"
                    remaining_args = args.extra_args
                else:
                    args.subcommand = "run"
                    remaining_args = args.extra_args
            else:
                args.subcommand = "run"
                remaining_args = []

            if args.subcommand == "run":
                run_parser = argparse.ArgumentParser()
                run_parser.add_argument("name", nargs="?")
                run_parser.add_argument("--id", type=str)
                run_args, _ = run_parser.parse_known_args(remaining_args)
                args.name = run_args.name
                args.id = run_args.id
                args.subfunc = self._inspect_run
            elif args.subcommand == "fleet":
                fleet_parser = argparse.ArgumentParser()
                fleet_parser.add_argument("name", nargs="?")
                fleet_parser.add_argument("--id", type=str)
                fleet_args, _ = fleet_parser.parse_known_args(remaining_args)
                args.name = fleet_args.name
                args.id = fleet_args.id
                args.subfunc = self._inspect_fleet
            elif args.subcommand == "volume":
                volume_parser = argparse.ArgumentParser()
                volume_parser.add_argument("name", nargs="?")
                volume_args, _ = volume_parser.parse_known_args(remaining_args)
                args.name = volume_args.name
                args.subfunc = self._inspect_volume
            elif args.subcommand == "gateway":
                gateway_parser = argparse.ArgumentParser()
                gateway_parser.add_argument("name", nargs="?")
                gateway_args, _ = gateway_parser.parse_known_args(remaining_args)
                args.name = gateway_args.name
                args.subfunc = self._inspect_gateway
        else:
            if not hasattr(args, "subfunc") or args.subfunc is None:
                if args.subcommand == "run":
                    args.subfunc = self._inspect_run
                elif args.subcommand == "fleet":
                    args.subfunc = self._inspect_fleet
                elif args.subcommand == "volume":
                    args.subfunc = self._inspect_volume
                elif args.subcommand == "gateway":
                    args.subfunc = self._inspect_gateway

        if not hasattr(args, "subfunc") or args.subfunc is None:
            args.subfunc = self._inspect_run
        args.subfunc(args)

    def _inspect_run(self, args: argparse.Namespace) -> None:
        if not args.name and not args.id:
            raise CLIError("Either name or --id must be provided")

        if args.name and args.id:
            raise CLIError("Cannot specify both name and --id")

        try:
            if args.id:
                run_id = UUID(args.id)
                run = self.api.client.runs.get(project_name=self.api.project, run_id=run_id)
            else:
                run = self.api.client.runs.get(self.api.project, args.name)
        except ResourceNotExistsError:
            console.print(f"Run [code]{args.name or args.id}[/] not found")
            exit(1)
        except ValueError:
            raise CLIError(f"Invalid UUID format: {args.id}")

        self._print_json(run)

    def _inspect_fleet(self, args: argparse.Namespace) -> None:
        if not args.name and not args.id:
            raise CLIError("Either name or --id must be provided")

        if args.name and args.id:
            raise CLIError("Cannot specify both name and --id")

        try:
            if args.id:
                fleet_id = UUID(args.id)
                fleet = self.api.client.fleets.get(self.api.project, fleet_id=fleet_id)
            else:
                fleet = self.api.client.fleets.get(self.api.project, args.name)
        except ResourceNotExistsError:
            console.print(f"Fleet [code]{args.name or args.id}[/] not found")
            exit(1)
        except ValueError:
            raise CLIError(f"Invalid UUID format: {args.id}")

        self._print_json(fleet)

    def _inspect_volume(self, args: argparse.Namespace) -> None:
        if not args.name:
            raise CLIError("Name must be provided")

        try:
            volume = self.api.client.volumes.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print("Volume not found")
            exit(1)

        self._print_json(volume)

    def _inspect_gateway(self, args: argparse.Namespace) -> None:
        if not args.name:
            raise CLIError("Name must be provided")

        try:
            gateway = self.api.client.gateways.get(
                project_name=self.api.project, gateway_name=args.name
            )
        except ResourceNotExistsError:
            console.print("Gateway not found")
            exit(1)

        self._print_json(gateway)

    def _print_json(self, obj: Union[Run, Fleet, Volume, Gateway]) -> None:
        print(pydantic_orjson_dumps_with_indent(obj.dict(), default=None))
