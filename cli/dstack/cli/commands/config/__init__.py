import sys
from argparse import Namespace

from dstack.cli.commands import BasicCommand
from dstack.cli.common import ask_choice
from dstack.api.config import list_dict


class ConfigCommand(BasicCommand):
    NAME = 'config'
    DESCRIPTION = 'Configure the backend'

    def __init__(self, parser):
        super(ConfigCommand, self).__init__(parser)

    def register(self):
        ...

    def _command(self, args: Namespace):
        configs = list_dict()
        config_name = ask_choice(title="Choose backend",
                                 values=list(configs.keys()),
                                 labels=list(configs.keys()),
                                 selected_value='aws')

        if not configs[config_name]:
            sys.exit(f"The backend '{config_name}' doesn't exist")

        configs[config_name].configure()
