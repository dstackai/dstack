import argparse
from pathlib import Path

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators import get_run_configurator_class
from dstack._internal.cli.services.configurators.run import BaseRunConfigurator
from dstack._internal.core.models.configurations import RunConfigurationType
from dstack._internal.utils.logging import get_logger
from dstack.api.utils import load_configuration

logger = get_logger(__name__)
NOTSET = object()


class RunCommand(APIBaseCommand):
    NAME = "run"
    DESCRIPTION = "Run a configuration"
    DEFAULT_HELP = False

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-h",
            "--help",
            nargs="?",
            type=RunConfigurationType,
            default=NOTSET,
            help="Show this help message and exit. TYPE is one of [code]task[/], [code]dev-environment[/], [code]service[/]",
            dest="help",
            metavar="TYPE",
        )
        self._parser.add_argument("working_dir")
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
        if args.help is not NOTSET:
            if args.help is not None:
                configurator_class = get_run_configurator_class(RunConfigurationType(args.help))
            else:
                configurator_class = BaseRunConfigurator
            configurator_class.register_args(self._parser)
            self._parser.print_help()
            return

        super()._command(args)

        logger.warning("[code]dstack run[/] is deprecated in favor of [code]dstack apply[/].")

        configuration_path, configuration = load_configuration(
            Path.cwd(), configuration_file=args.configuration_file
        )
        configurator_class = get_run_configurator_class(configuration.type)
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
