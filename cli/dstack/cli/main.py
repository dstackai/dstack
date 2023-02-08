import argparse
import sys

from dstack.cli.handlers import cli_initialize
from dstack.version import __version__ as version


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Not sure where to start? Call dstack config, followed by dstack init.\n"
            "Define workflows within .dstack/workflows and run them via dstack run.\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Run 'dstack COMMAND --help' for more information on a particular command.\n\n"
            "For more details, check https://docs.dstack.ai/reference/cli.\n "
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
        exit(1)
    args, unknown = parser.parse_known_args()
    args.unknown = unknown
    args.func(args)


if __name__ == "__main__":
    main()
