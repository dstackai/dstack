import argparse
import sys

from rich_argparse import RichHelpFormatter

from dstack._internal.cli.common import check_cli_errors
from dstack._internal.cli.handlers import cli_initialize
from dstack.version import __version__ as version


def main():
    RichHelpFormatter.usage_markup = True
    RichHelpFormatter.styles["argparse.args"] = "bold sea_green3"
    RichHelpFormatter.styles["argparse.groups"] = "bold grey74"
    RichHelpFormatter.styles["argparse.text"] = "grey74"
    parser = argparse.ArgumentParser(
        description=(
            "Not sure where to start? Call [bold sea_green3]dstack init[/bold sea_green3].\n"
            "Define workflows within [bold sea_green3].dstack/workflows[/bold sea_green3] and run them via [bold sea_green3]dstack run[/bold sea_green3].\n"
        ),
        formatter_class=RichHelpFormatter,
        epilog=(
            "Run [bold sea_green3]dstack COMMAND --help[/bold sea_green3] for more information on a particular command.\n\n"
            "For more details, check https://dstack.ai/docs.\n "
        ),
        add_help=False,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{version}",
        help="Show dstack version",
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit",
    )
    parser.set_defaults(func=lambda _: parser.print_help())
    subparsers = parser.add_subparsers(metavar="COMMAND")

    cli_initialize(parser=subparsers)

    if len(sys.argv) < 2:
        parser.print_help()
        exit(0)
    args, unknown = parser.parse_known_args()
    args.unknown = unknown
    check_cli_errors(args.func)(args)


if __name__ == "__main__":
    main()
