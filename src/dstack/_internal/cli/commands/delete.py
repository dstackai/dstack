import argparse
from pathlib import Path

from argcomplete import FilesCompleter

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators import (
    get_apply_configurator_class,
    load_apply_configuration,
)


class DeleteCommand(APIBaseCommand):
    NAME = "delete"
    DESCRIPTION = "Delete resources"
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
        ).completer = FilesCompleter(allowednames=["*.yml", "*.yaml"])
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for confirmation",
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        configuration_path, configuration = load_apply_configuration(args.configuration_file)
        configurator_class = get_apply_configurator_class(configuration.type)
        configurator = configurator_class(api_client=self.api)
        configurator.delete_configuration(
            conf=configuration,
            configuration_path=configuration_path,
            command_args=args,
        )
