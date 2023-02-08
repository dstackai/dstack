from argparse import Namespace

from dstack.api.config import list_dict
from dstack.cli.commands import BasicCommand


class ConfigCommand(BasicCommand):
    NAME = "config"
    DESCRIPTION = "Configure the backend"

    def __init__(self, parser):
        super(ConfigCommand, self).__init__(parser)

    def register(self):
        ...

    def _command(self, args: Namespace):
        configs = list_dict()
        configs["aws"].configure()
