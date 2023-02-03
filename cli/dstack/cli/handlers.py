from dstack.cli.commands import BasicCommand
import dstack.cli.commands.run
import dstack.cli.commands.config

# import dstack.cli.commands.hub
import dstack.cli.commands.init
import dstack.cli.commands.logs
import dstack.cli.commands.ls
import dstack.cli.commands.ps
import dstack.cli.commands.pull
import dstack.cli.commands.push
import dstack.cli.commands.rm
import dstack.cli.commands.run
import dstack.cli.commands.secrets
import dstack.cli.commands.stop
import dstack.cli.commands.tags


def cli_initialize(parser):
    commands = [
        cls(parser=parser) for cls in sorted(BasicCommand.__subclasses__(), key=lambda x: str(x))
    ]  # pylint: disable=E1101
    for command in commands:
        command.register()
