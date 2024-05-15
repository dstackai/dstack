import argparse
from pathlib import Path

import yaml

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators import (
    get_apply_configurator_class,
)
from dstack._internal.cli.utils.common import cli_error
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    AnyApplyConfiguration,
    parse_apply_configuration,
)


class ApplyCommand(APIBaseCommand):
    NAME = "apply"
    DESCRIPTION = "Apply dstack configuration"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "configuration_file",
            help="The path to the configuration file",
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
            configuration = _load_configuration(args.configuration_file)
        except ConfigurationError as e:
            raise cli_error(e)
        configurator_class = get_apply_configurator_class(configuration.type)
        configurator = configurator_class(api_client=self.api)
        configurator.apply_configuration(conf=configuration, args=args)


def _load_configuration(configuration_file: str) -> AnyApplyConfiguration:
    configuration_path = Path(configuration_file)
    if not configuration_path.exists():
        raise ConfigurationError(f"Configuration file {configuration_file} does not exist")
    try:
        with open(configuration_path, "r") as f:
            conf = parse_apply_configuration(yaml.safe_load(f))
    except OSError:
        raise ConfigurationError(f"Failed to load configuration from {configuration_path}")
    return conf
