import argparse

import argcomplete
from rich.markup import escape
from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands.apply import ApplyCommand
from dstack._internal.cli.commands.attach import AttachCommand
from dstack._internal.cli.commands.completion import CompletionCommand
from dstack._internal.cli.commands.config import ConfigCommand
from dstack._internal.cli.commands.delete import DeleteCommand
from dstack._internal.cli.commands.fleet import FleetCommand
from dstack._internal.cli.commands.gateway import GatewayCommand
from dstack._internal.cli.commands.init import InitCommand
from dstack._internal.cli.commands.logs import LogsCommand
from dstack._internal.cli.commands.metrics import MetricsCommand
from dstack._internal.cli.commands.offer import OfferCommand
from dstack._internal.cli.commands.project import ProjectCommand
from dstack._internal.cli.commands.ps import PsCommand
from dstack._internal.cli.commands.secrets import SecretCommand
from dstack._internal.cli.commands.server import ServerCommand
from dstack._internal.cli.commands.stats import StatsCommand
from dstack._internal.cli.commands.stop import StopCommand
from dstack._internal.cli.commands.volume import VolumeCommand
from dstack._internal.cli.utils.common import _colors, console
from dstack._internal.cli.utils.updates import check_for_updates
from dstack._internal.core.errors import ClientError, CLIError, ConfigurationError, SSHError
from dstack._internal.core.services.ssh.client import get_ssh_client_info
from dstack._internal.utils.logging import get_logger
from dstack.version import __version__ as version

logger = get_logger(__name__)


def main():
    RichHelpFormatter.usage_markup = True
    RichHelpFormatter.styles["code"] = _colors["code"]
    RichHelpFormatter.styles["argparse.args"] = _colors["code"]
    RichHelpFormatter.styles["argparse.groups"] = "bold grey74"
    RichHelpFormatter.styles["argparse.text"] = "grey74"

    parser = argparse.ArgumentParser(
        description=(
            "Not sure where to start?"
            " Define a [code].dstack.yml[/] configuration file and run it via [code]dstack apply[/]\n"
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
    ApplyCommand.register(subparsers)
    AttachCommand.register(subparsers)
    ConfigCommand.register(subparsers)
    DeleteCommand.register(subparsers)
    FleetCommand.register(subparsers)
    GatewayCommand.register(subparsers)
    InitCommand.register(subparsers)
    OfferCommand.register(subparsers)
    LogsCommand.register(subparsers)
    MetricsCommand.register(subparsers)
    ProjectCommand.register(subparsers)
    PsCommand.register(subparsers)
    SecretCommand.register(subparsers)
    ServerCommand.register(subparsers)
    StatsCommand.register(subparsers)
    StopCommand.register(subparsers)
    VolumeCommand.register(subparsers)
    CompletionCommand.register(subparsers)

    argcomplete.autocomplete(parser, always_complete_options=False)

    args, unknown_args = parser.parse_known_args()
    args.unknown = unknown_args

    try:
        check_for_updates()
        get_ssh_client_info()
        args.func(args)
    except (ClientError, CLIError, ConfigurationError, SSHError) as e:
        console.print(f"[error]{escape(str(e))}[/]")
        logger.debug(e, exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
