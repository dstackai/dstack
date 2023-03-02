from argparse import Namespace

from dstack.api.config import dict_configurator
from dstack.cli.commands import BasicCommand
from dstack.cli.common import ask_choice


class ConfigCommand(BasicCommand):
    NAME = "config"
    DESCRIPTION = "Configure the backend"

    def __init__(self, parser):
        super(ConfigCommand, self).__init__(parser)

    def register(self):
        pass

    def _command(self, args: Namespace):
        configurators = dict_configurator()
        if args.unknown is not None and len(args.unknown) != 0:
            configurators[args.unknown[0]].parse_args(args.unknown[1:])
        elif len(configurators) > 1:
            backend_name = ask_choice(
                "Choose backend",
                [f"[{key}]" for key in configurators.keys()],
                [key for key in configurators.keys()],
                "aws",
            )
            configurators[backend_name].configure_cli()
        else:
            configurators["aws"].configure_cli()
