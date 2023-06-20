from dstack._internal.cli.commands.build import BuildCommand
from dstack._internal.cli.commands.config import ConfigCommand
from dstack._internal.cli.commands.cp import CpCommand
from dstack._internal.cli.commands.init import InitCommand
from dstack._internal.cli.commands.logs import LogCommand
from dstack._internal.cli.commands.ls import LsCommand
from dstack._internal.cli.commands.prune import PruneCommand
from dstack._internal.cli.commands.ps import PSCommand
from dstack._internal.cli.commands.rm import RMCommand
from dstack._internal.cli.commands.run import RunCommand
from dstack._internal.cli.commands.secrets import SecretCommand
from dstack._internal.cli.commands.start import StartCommand
from dstack._internal.cli.commands.stop import StopCommand
from dstack._internal.cli.commands.tags import TAGCommand

commands_classes = [
    ConfigCommand,
    CpCommand,
    InitCommand,
    LogCommand,
    LsCommand,
    BuildCommand,
    PruneCommand,
    PSCommand,
    RMCommand,
    RunCommand,
    SecretCommand,
    StartCommand,
    StopCommand,
    TAGCommand,
]


def cli_initialize(parser):
    commands = [cls(parser=parser) for cls in commands_classes]
    for command in commands:
        command.register()
