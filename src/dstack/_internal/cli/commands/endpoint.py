import argparse
import os
from pathlib import Path

from argcomplete import FilesCompleter  # type: ignore[attr-defined]

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.models.endpoint_presets import EndpointPresetListOutput
from dstack._internal.cli.models.endpoints import EndpointConfiguration
from dstack._internal.cli.services.completion import ProjectNameCompleter
from dstack._internal.cli.services.endpoints.apply import apply_endpoint_preset
from dstack._internal.cli.services.endpoints.create import create_endpoint_preset
from dstack._internal.cli.services.endpoints.output import print_endpoint_presets
from dstack._internal.cli.services.endpoints.store import (
    EndpointPresetStore,
    load_endpoint_configuration,
)
from dstack._internal.cli.services.profile import apply_profile_args, register_profile_args
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.services import is_valid_dstack_resource_name
from dstack.api import Client
from dstack.api.utils import load_profile


class EndpointCommand(BaseCommand):
    NAME = "endpoint"
    DESCRIPTION = "Manage model inference endpoints"

    def _register(self) -> None:
        self._parser.add_argument(
            "--project",
            help="The name of the project. Defaults to [code]$DSTACK_PROJECT[/]",
            metavar="NAME",
            default=os.getenv("DSTACK_PROJECT"),
        ).completer = ProjectNameCompleter()  # type: ignore[attr-defined]
        self._parser.set_defaults(subfunc=lambda _: self._parser.print_help())
        subparsers = self._parser.add_subparsers(dest="action")
        preset_parser = subparsers.add_parser(
            "preset",
            help="Manage endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        _add_list_args(preset_parser)
        preset_parser.set_defaults(subfunc=self._list)
        preset_subparsers = preset_parser.add_subparsers(dest="preset_action")

        list_parser = preset_subparsers.add_parser(
            "list",
            help="List endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        _add_list_args(list_parser)
        list_parser.set_defaults(subfunc=self._list)

        get_parser = preset_subparsers.add_parser(
            "get",
            help="Get an endpoint preset",
            formatter_class=self._parser.formatter_class,
        )
        get_parser.add_argument("preset", metavar="ID", help="The preset ID")
        get_parser.add_argument(
            "--json",
            action="store_true",
            required=True,
            help="Output in JSON format",
        )
        get_parser.set_defaults(subfunc=self._get)

        create_parser = preset_subparsers.add_parser(
            "create",
            help="Create an endpoint preset",
            formatter_class=self._parser.formatter_class,
        )
        _add_configuration_args(create_parser)
        register_profile_args(create_parser)
        create_parser.add_argument(
            "--keep-service",
            action="store_true",
            help="Leave the verified service running",
        )
        create_parser.add_argument(
            "--debug",
            action="store_true",
            help="Save the agent prompt and raw trace",
        )
        create_parser.set_defaults(subfunc=self._create)

        apply_parser = preset_subparsers.add_parser(
            "apply",
            help="Apply an endpoint preset",
            formatter_class=self._parser.formatter_class,
        )
        _add_configuration_args(apply_parser)
        register_profile_args(apply_parser)
        apply_parser.add_argument("--preset", metavar="ID", help="The preset ID to use")
        apply_parser.add_argument(
            "-y", "--yes", action="store_true", help="Do not ask for confirmation"
        )
        apply_parser.add_argument(
            "--force", action="store_true", help="Force apply when no changes are detected"
        )
        apply_parser.add_argument(
            "-d", "--detach", action="store_true", help="Exit after submitting the service"
        )
        apply_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show all plan properties"
        )
        apply_parser.set_defaults(subfunc=self._apply)

        delete_parser = preset_subparsers.add_parser(
            "delete",
            help="Delete endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        delete_target = delete_parser.add_mutually_exclusive_group(required=True)
        delete_target.add_argument(
            "preset",
            nargs="?",
            metavar="ID",
            help="The preset ID",
        )
        delete_target.add_argument(
            "--model",
            metavar="MODEL",
            help="Delete all presets for a base model",
        )
        delete_parser.add_argument(
            "-y", "--yes", action="store_true", help="Do not ask for confirmation"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace) -> None:
        super()._command(args)
        try:
            args.subfunc(args)
        except KeyboardInterrupt:
            console.print("\nOperation interrupted by user. Exiting...")
            exit(0)

    def _list(self, args: argparse.Namespace) -> None:
        presets = EndpointPresetStore().list()
        if getattr(args, "json", False):
            print(EndpointPresetListOutput(presets=presets).json())
            return
        print_endpoint_presets(presets, verbose=getattr(args, "verbose", False))

    def _create(self, args: argparse.Namespace) -> None:
        _, configuration = load_endpoint_configuration(args.configuration_file)
        configuration = _get_effective_configuration(configuration, args)
        result = create_endpoint_preset(
            api=Client.from_config(project_name=args.project),
            configuration=configuration,
            store=EndpointPresetStore(),
            keep_service=args.keep_service,
            debug=args.debug,
        )
        console.print(
            f"Endpoint preset [code]{result.preset.id}[/] for "
            f"[code]{result.preset.base}[/] saved to [code]{result.path}[/]"
        )
        if args.keep_service:
            console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def _get(self, args: argparse.Namespace) -> None:
        preset = EndpointPresetStore().get(args.preset)
        if preset is None:
            raise CLIError(f"Endpoint preset {args.preset!r} does not exist")
        print(preset.json())

    def _apply(self, args: argparse.Namespace) -> None:
        configuration_path, configuration = load_endpoint_configuration(args.configuration_file)
        configuration = _get_effective_configuration(configuration, args)
        apply_endpoint_preset(
            api=Client.from_config(project_name=args.project),
            configuration=configuration,
            configuration_path=configuration_path,
            preset_id=args.preset or configuration.preset,
            profile_name=args.profile,
            command_args=args,
            store=EndpointPresetStore(),
        )

    def _delete(self, args: argparse.Namespace) -> None:
        store = EndpointPresetStore()
        preset = None
        if args.preset is not None:
            preset = store.get(args.preset)
            if preset is None:
                raise CLIError(f"Endpoint preset {args.preset!r} does not exist")
            message = f"Delete endpoint preset [code]{preset.id}[/] for [code]{preset.base}[/]?"
        else:
            presets = [preset for preset in store.list() if preset.base == args.model]
            if not presets:
                raise CLIError(f"No endpoint presets found for base model {args.model!r}")
            message = (
                f"Delete {len(presets)} endpoint preset"
                f"{'s' if len(presets) != 1 else ''} for [code]{args.model}[/]?"
            )
        if not args.yes and not confirm_ask(message):
            console.print("\nExiting...")
            return
        if args.preset is not None:
            assert preset is not None
            store.delete(args.preset)
            console.print(
                f"Endpoint preset [code]{preset.id}[/] for [code]{preset.base}[/] deleted"
            )
        else:
            count = store.delete_for_base(args.model)
            console.print(
                f"Deleted {count} endpoint preset{'s' if count != 1 else ''} "
                f"for [code]{args.model}[/]"
            )


def _add_configuration_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-f",
        "--file",
        required=True,
        metavar="FILE",
        dest="configuration_file",
        help="The endpoint configuration file",
    ).completer = FilesCompleter(allowednames=["*.yml", "*.yaml"])  # type: ignore[attr-defined]
    parser.add_argument(
        "-n",
        "--name",
        metavar="NAME",
        help="The endpoint name. Required when the configuration omits name",
    )


def _add_list_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )


def _apply_name(configuration: EndpointConfiguration, name: str | None) -> None:
    if name is not None:
        configuration.name = name
    if configuration.name is None:
        raise CLIError("Endpoint name is required. Set `name` in the configuration or use --name")
    if not is_valid_dstack_resource_name(configuration.name):
        raise CLIError("Endpoint name must match '^[a-z][a-z0-9-]{1,40}$'")


def _get_effective_configuration(
    configuration: EndpointConfiguration,
    args: argparse.Namespace,
) -> EndpointConfiguration:
    _apply_name(configuration, args.name)
    profile = load_profile(Path.cwd(), args.profile)
    for field in ProfileParams.__fields__:
        if getattr(configuration, field) is None:
            setattr(configuration, field, getattr(profile, field))
    apply_profile_args(args, configuration)
    return EndpointConfiguration.parse_obj(configuration.dict())
