import argparse

from argcomplete import FilesCompleter  # type: ignore[attr-defined]

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators import (
    APPLY_STDIN_NAME,
    get_apply_configurator_class,
    load_apply_configuration,
)
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ApplyConfigurationType

NOTSET = object()


class ApplyCommand(APIBaseCommand):
    NAME = "apply"
    DESCRIPTION = "Apply a configuration"
    DEFAULT_HELP = False

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-h",
            "--help",
            nargs="?",
            type=ApplyConfigurationType,
            default=NOTSET,
            help="Show this help message and exit.",
            dest="help",
            metavar="TYPE",
        )
        self._parser.add_argument(
            "-f",
            "--file",
            metavar="FILE",
            help=(
                "The path to the configuration file."
                " Specify [code]-[/] to read configuration from stdin."
                " Defaults to [code]$PWD/.dstack.yml[/]"
            ),
            dest="configuration_file",
        ).completer = FilesCompleter(allowednames=["*.yml", "*.yaml"])  # type: ignore[attr-defined]
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for confirmation",
            action="store_true",
        )
        self._parser.add_argument(
            "--force",
            help="Force apply when no changes detected",
            action="store_true",
        )
        self._parser.add_argument(
            "-d",
            "--detach",
            help="Exit immediately after submitting configuration",
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        try:
            if args.help is not NOTSET:
                if args.help is not None:
                    configurator_class = get_apply_configurator_class(
                        ApplyConfigurationType(args.help)
                    )
                    configurator_class.register_args(self._parser)
                    self._parser.print_help()
                    return
                self._parser.print_help()
                console.print(
                    "\nType `dstack apply -h CONFIGURATION_TYPE` to see configuration-specific options.\n"
                )
                return

            super()._command(args)
            if not args.yes and args.configuration_file == APPLY_STDIN_NAME:
                raise CLIError("Cannot read configuration from stdin if -y/--yes is not specified")
            configuration_path, configuration = load_apply_configuration(args.configuration_file)
            configurator_class = get_apply_configurator_class(configuration.type)
            configurator = configurator_class(api_client=self.api)
            configurator_parser = configurator.get_parser()
            known, unknown = configurator_parser.parse_known_args(args.unknown)
            configurator.apply_configuration(
                conf=configuration,
                configuration_path=configuration_path,
                command_args=args,
                configurator_args=known,
                unknown_args=unknown,
            )
        except KeyboardInterrupt:
            console.print("\nOperation interrupted by user. Exiting...")
            exit(0)
