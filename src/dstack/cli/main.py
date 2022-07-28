import sys
from argparse import ArgumentParser, SUPPRESS, Namespace

from dstack.cli import app, logs, run, stop, artifacts, runs, runners, init, \
    restart, prune, tag, untag, config
from dstack.version import __version__ as version


def default_func(_: Namespace):
    print("Usage: dstack [OPTIONS ...] COMMAND [ARGS ...]\n"
          "\n"
          "The available commands for execution are listed below.\n"
          "The primary commands are given first, followed by\n"
          "less common or more advanced commands.\n"
          "\n"
          "Main commands:\n"
          "  run            Run a workflow\n"
          "  runs           Show recent runs\n"
          "  stop           Stop a run\n"
          "  restart        Restart a run\n"
          "  logs           Show logs of a run\n"
          "  artifacts      Show or download artifacts of a run\n"
          "  app            Open a running application\n"
          "\n"
          "Other commands:\n"
          "  init           Initialize the project repository\n"
          "  config         Configure your token\n"
          "  prune          Delete all finished untagged runs\n"
          "  tag            Assign a tag to a run\n"
          "  untag          Delete a tag\n"
          "\n"
          "Options:\n"
          "  -h, --help     Show this help output, or the help for a specified command.\n"
          "  -v, --version  Show the version of the CLI.\n"
          "\n"
          "For more information, visit https://docs.dstack.ai/cli"
          )


def main():
    parser = ArgumentParser(epilog="Please visit https://docs.dstack.ai for more information",
                            add_help=False)
    parser.add_argument("-v", "--version", action="version", version=f"{version}", help="Show program's version")
    parser.add_argument('-h', '--help', action='store_true', default=SUPPRESS,
                        help='Show this help message and exit')
    parser.set_defaults(func=default_func)

    subparsers = parser.add_subparsers()

    app.register_parsers(subparsers)
    artifacts.register_parsers(subparsers)
    # on_demand.register_parsers(subparsers)
    # aws.register_parsers(subparsers)
    config.register_parsers(subparsers)
    init.register_parsers(subparsers)
    # login.register_parsers(subparsers)
    # logout.register_parsers(subparsers)
    logs.register_parsers(subparsers)
    prune.register_parsers(subparsers)
    # TODO: Rename to restart
    restart.register_parsers(subparsers)
    run.register_parsers(subparsers)
    # TODO: Hide
    runners.register_parsers(subparsers)
    runs.register_parsers(subparsers)
    stop.register_parsers(subparsers)
    # TODO: Merge tag and untag to tags
    tag.register_parsers(subparsers)
    # token.register_parsers(subparsers)
    untag.register_parsers(subparsers)

    if len(sys.argv) < 2:
        parser.print_help()
        exit(1)

    args, unknown = parser.parse_known_args()
    args.unknown = unknown
    args.func(args)


if __name__ == '__main__':
    main()
