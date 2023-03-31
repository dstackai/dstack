from argparse import Namespace

from dstack.api.backend import get_current_remote_backend
from dstack.api.config import dict_configurator
from dstack.cli.commands import BasicCommand
from dstack.cli.common import ask_choice, console


class ConfigCommand(BasicCommand):
    NAME = "config"
    DESCRIPTION = "Configure the remote backend"

    def __init__(self, parser):
        super(ConfigCommand, self).__init__(parser)

    def register(self):
        subparsers = self._parser.add_subparsers(metavar="BACKEND")
        configurators = dict_configurator()
        for configurator in configurators.values():
            configurator.register_parser(subparsers)

    def _command(self, args: Namespace):
        default_backend_name = None
        remote_backend = get_current_remote_backend()
        if remote_backend is not None:
            default_backend_name = remote_backend.name
        try:
            configurators = dict_configurator()
            backend_name = ask_choice(
                "Choose backend",
                [f"[{key}]" for key in configurators.keys()],
                [key for key in configurators.keys()],
                default_backend_name,
            )
            configurators[backend_name].configure_cli()
        except KeyboardInterrupt:
            console.print("Configuration canceled")
            exit(1)
