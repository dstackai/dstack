import sys
from argparse import ArgumentParser, SUPPRESS

import colorama

from dstack.cli import logs, run, stop, aws, artifacts, status, runners, init, \
    on_demand, resume, prune, tag, untag, config
from dstack.version import __version__ as version


def main():
    colorama.init()

    parser = ArgumentParser(epilog="Please visit https://docs.dstack.ai for more information",
                            add_help=False)
    parser.add_argument("-v", "--version", action="version", version=f"{version}", help="Show program's version")
    parser.add_argument('-h', '--help', action='help', default=SUPPRESS,
                        help='Show this help message and exit')
    subparsers = parser.add_subparsers()

    artifacts.register_parsers(subparsers)
    on_demand.register_parsers(subparsers)
    aws.register_parsers(subparsers)
    config.register_parsers(subparsers)
    init.register_parsers(subparsers)
    # login.register_parsers(subparsers)
    # logout.register_parsers(subparsers)
    logs.register_parsers(subparsers)
    prune.register_parsers(subparsers)
    resume.register_parsers(subparsers)
    run.register_parsers(subparsers, parser)
    runners.register_parsers(subparsers)
    status.register_parsers(subparsers)
    stop.register_parsers(subparsers)
    tag.register_parsers(subparsers)
    # token.register_parsers(subparsers)
    untag.register_parsers(subparsers)

    if len(sys.argv) < 2:
        parser.print_help()
        exit(1)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
