import argparse
from pathlib import Path

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators import (
    get_apply_configurator_class,
    load_apply_configuration,
)


class ApplyCommand(APIBaseCommand):
    NAME = "apply"
    DESCRIPTION = "Apply dstack configuration"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-f",
            "--file",
            type=Path,
            metavar="FILE",
            help="The path to the configuration file. Defaults to [code]$PWD/.dstack.yml[/]",
            dest="configuration_file",
        )
        self._parser.add_argument(
            "--force",
            help="Force apply when no changes detected",
            action="store_true",
        )
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for confirmation",
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        configuration = load_apply_configuration(args.configuration_file)
        configurator_class = get_apply_configurator_class(configuration.type)
        configurator = configurator_class(api_client=self.api)
        configurator_parser = configurator.get_parser()
        known, unknown = configurator_parser.parse_known_args(args.unknown)
        configurator.apply_configuration(
            conf=configuration,
            command_args=args,
            configurator_args=known,
            unknown_args=unknown,
        )
