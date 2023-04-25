from argparse import Namespace

from dstack.api.hub._config import HubConfigurator
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console


class ConfigCommand(BasicCommand):
    NAME = "config"
    DESCRIPTION = "Configure hub"

    def __init__(self, parser):
        super(ConfigCommand, self).__init__(parser)
        self.configurator = HubConfigurator()

    def register(self):
        subparsers = self._parser.add_subparsers(metavar="BACKEND")
        self.configurator.register_parser(subparsers)

    def _command(self, args: Namespace):
        try:
            self.configurator.configure_cli(args)
        except KeyboardInterrupt:
            console.print("Configuration canceled")
            exit(1)
