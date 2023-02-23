from argparse import Namespace

from dstack.api.config import dict_config
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
        configs = dict_config()
        if len(configs) > 1:
            backend_name = ask_choice(
                "Choose backend",
                [f"[{key}]" for key in configs.keys()],
                [key for key in configs.keys()],
                "aws",
            )
            configs[backend_name].configure()
        else:
            configs["aws"].configure()
