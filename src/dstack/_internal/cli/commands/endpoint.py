import argparse
import os

from argcomplete import FilesCompleter  # type: ignore[attr-defined]

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.services.completion import ProjectNameCompleter
from dstack._internal.cli.services.endpoint_preset_apply import apply_endpoint_preset
from dstack._internal.cli.services.endpoint_preset_create import create_endpoint_preset
from dstack._internal.cli.services.endpoint_presets import (
    EndpointPresetStore,
    load_endpoint_configuration,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.endpoint_presets import print_endpoint_presets
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.services import is_valid_dstack_resource_name
from dstack.api import Client


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
        preset_parser.set_defaults(subfunc=self._list)
        preset_subparsers = preset_parser.add_subparsers(dest="preset_action")

        list_parser = preset_subparsers.add_parser(
            "list",
            help="List endpoint presets",
            formatter_class=self._parser.formatter_class,
        )
        list_parser.add_argument("-v", "--verbose", action="store_true")
        list_parser.set_defaults(subfunc=self._list)

        create_parser = preset_subparsers.add_parser(
            "create",
            help="Create an endpoint preset",
            formatter_class=self._parser.formatter_class,
        )
        _add_configuration_args(create_parser)
        create_parser.add_argument(
            "--keep-service",
            action="store_true",
            help="Leave the verified service running",
        )
        create_parser.set_defaults(subfunc=self._create)

        apply_parser = preset_subparsers.add_parser(
            "apply",
            help="Apply an endpoint preset",
            formatter_class=self._parser.formatter_class,
        )
        _add_configuration_args(apply_parser)
        apply_parser.add_argument("--recipe", metavar="ID", help="The recipe ID to use")
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
            help="Delete an endpoint preset or recipe",
            formatter_class=self._parser.formatter_class,
        )
        delete_target = delete_parser.add_mutually_exclusive_group(required=True)
        delete_target.add_argument(
            "base",
            nargs="?",
            metavar="BASE",
            help="The base model whose preset to delete",
        )
        delete_target.add_argument(
            "--recipe",
            metavar="ID",
            help="Delete one recipe by ID",
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
        print_endpoint_presets(
            EndpointPresetStore().list(),
            verbose=getattr(args, "verbose", False),
        )

    def _create(self, args: argparse.Namespace) -> None:
        _, configuration = load_endpoint_configuration(args.configuration_file)
        _apply_name(configuration, args.name)
        _resolve_endpoint_env(configuration)
        result = create_endpoint_preset(
            api=Client.from_config(project_name=args.project),
            configuration=configuration,
            store=EndpointPresetStore(),
            keep_service=args.keep_service,
        )
        console.print(
            f"Endpoint preset recipe [code]{result.recipe.id}[/] for "
            f"[code]{result.recipe.base}[/] saved to [code]{result.path}[/]"
        )
        if args.keep_service:
            console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def _apply(self, args: argparse.Namespace) -> None:
        configuration_path, configuration = load_endpoint_configuration(args.configuration_file)
        _apply_name(configuration, args.name)
        apply_endpoint_preset(
            api=Client.from_config(project_name=args.project),
            configuration=configuration,
            configuration_path=configuration_path,
            recipe_id=args.recipe or configuration.recipe,
            command_args=args,
            store=EndpointPresetStore(),
        )

    def _delete(self, args: argparse.Namespace) -> None:
        store = EndpointPresetStore()
        recipe = None
        if args.recipe is not None:
            recipe = store.get(args.recipe)
            if recipe is None:
                raise CLIError(f"Endpoint preset recipe {args.recipe!r} does not exist")
            message = (
                f"Delete endpoint preset recipe [code]{recipe.id}[/] for [code]{recipe.base}[/]?"
            )
        else:
            recipes = [recipe for recipe in store.list() if recipe.base == args.base]
            if not recipes:
                raise CLIError(f"Endpoint preset {args.base!r} does not exist")
            message = (
                f"Delete endpoint preset [code]{args.base}[/] and its "
                f"{len(recipes)} recipe{'s' if len(recipes) != 1 else ''}?"
            )
        if not args.yes and not confirm_ask(message):
            console.print("\nExiting...")
            return
        if args.recipe is not None:
            assert recipe is not None
            store.delete_recipe(args.recipe)
            console.print(
                f"Endpoint preset recipe [code]{recipe.id}[/] for [code]{recipe.base}[/] deleted"
            )
        else:
            count = store.delete_preset(args.base)
            console.print(
                f"Endpoint preset [code]{args.base}[/] deleted "
                f"({count} recipe{'s' if count != 1 else ''})"
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


def _apply_name(configuration: EndpointConfiguration, name: str | None) -> None:
    if name is not None:
        configuration.name = name
    if configuration.name is None:
        raise CLIError("Endpoint name is required. Set `name` in the configuration or use --name")
    if not is_valid_dstack_resource_name(configuration.name):
        raise CLIError("Endpoint name must match '^[a-z][a-z0-9-]{1,40}$'")


def _resolve_endpoint_env(configuration: EndpointConfiguration) -> None:
    for key, value in configuration.env.items():
        if not isinstance(value, EnvSentinel):
            continue
        try:
            configuration.env[key] = value.from_env(os.environ)
        except ValueError as e:
            raise ConfigurationError(str(e)) from e
