from argparse import Namespace

from dstack.api.backend import get_current_remote_backend
from dstack.api.config import dict_config
from dstack.cli.commands import BasicCommand
from dstack.cli.common import ask_choice


class ConfigCommand(BasicCommand):
    NAME = "config"
    DESCRIPTION = "Configure the remote backend"

    def __init__(self, parser):
        super(ConfigCommand, self).__init__(parser)

    def register(self):
        pass

    def _command(self, args: Namespace):
        configs = dict_config()
        default_backend_name = None
        remote_backend = get_current_remote_backend()
        if remote_backend is not None:
            default_backend_name = remote_backend.name
        backend_name = ask_choice(
            "Choose backend",
            [f"[{key}]" for key in configs.keys()],
            [key for key in configs.keys()],
            default_backend_name,
        )
        configs[backend_name].configure()
