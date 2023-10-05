import argparse

from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands.init import InitCommand
from dstack._internal.cli.commands.ps import PsCommand
from dstack._internal.cli.commands.run import RunCommand
from dstack._internal.cli.commands.server import ServerCommand
from dstack._internal.cli.commands.stop import StopCommand
from dstack._internal.cli.utils.common import colors, console
from dstack._internal.core.errors import ClientError, CLIError
from dstack.version import __version__ as version


def main():
    RichHelpFormatter.usage_markup = True
    RichHelpFormatter.styles["code"] = colors["code"]
    RichHelpFormatter.styles["argparse.args"] = colors["code"]
    RichHelpFormatter.styles["argparse.groups"] = "bold grey74"
    RichHelpFormatter.styles["argparse.text"] = "grey74"

    parser = argparse.ArgumentParser(
        description=(
            "Not sure where to start? Call [code]dstack init[/].\n"
            "Define [code].dstack.yml[/] configuration and run it via [code]dstack run[/].\n"
        ),
        formatter_class=RichHelpFormatter,
        epilog=(
            "Run [code]dstack COMMAND --help[/] for more information on a particular command.\n\n"
            "For more details, check https://dstack.ai/docs.\n "
        ),
        add_help=True,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{version}",
        help="Show dstack version",
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
    except (ClientError, CLIError) as e:
        console.print(f"[error]{e}[/]")
        exit(1)


if __name__ == "__main__":
    main()
