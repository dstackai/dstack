import argparse

from dstack._internal.cli.commands.init import InitCommand
from dstack._internal.cli.commands.ps import PsCommand
from dstack._internal.cli.commands.run import RunCommand
from dstack._internal.cli.commands.server import ServerCommand
from dstack._internal.cli.commands.stop import StopCommand
from dstack._internal.core.errors import CLIError
from dstack.version import __version__ as version


def main():
    parser = argparse.ArgumentParser(add_help=True)
    # todo Rich
    parser.add_argument(
        "-v", "--version", action="version", version=f"{version}", help="show dstack version"
    )
    parser.set_defaults(func=lambda _: parser.print_help())

    subparsers = parser.add_subparsers(metavar="COMMAND")
    InitCommand.register(subparsers)
    PsCommand.register(subparsers)
    RunCommand.register(subparsers)
    ServerCommand.register(subparsers)
    StopCommand.register(subparsers)

    args, unknown_args = parser.parse_known_args()
    args.unknown = unknown_args
    try:
        args.func(args)
    except CLIError as e:
        print(e)
        exit(1)


if __name__ == "__main__":
    main()
