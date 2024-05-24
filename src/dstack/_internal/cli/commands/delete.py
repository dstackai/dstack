import argparse
from pathlib import Path

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators import (
    get_apply_configurator_class,
    load_apply_configuration,
)
from dstack._internal.cli.utils.common import cli_error
from dstack._internal.core.errors import ConfigurationError


class DeleteCommand(APIBaseCommand):
    NAME = "delete"
    DESCRIPTION = "Delete resources defined by dstack configuration"
    ALIASES = ["destroy"]

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
            "-y",
            "--yes",
            help="Do not ask for confirmation",
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        try:
            configuration = load_apply_configuration(args.configuration_file)
        except ConfigurationError as e:
            raise cli_error(e)
        configurator_class = get_apply_configurator_class(configuration.type)
        configurator = configurator_class(api_client=self.api)
        configurator.delete_configuration(conf=configuration, args=args)
