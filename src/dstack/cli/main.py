import sys
from argparse import ArgumentParser, SUPPRESS, Namespace

from dstack.cli import app, logs, run, stop, artifacts, status, init, \
    restart, delete, tags, config, dashboard, secrets
from dstack.version import __version__ as version


def default_func(_: Namespace):
    print("Usage: dstack [OPTIONS ...] COMMAND [ARGS ...]\n"
          "\n"
          "Main commands:\n"
          "  run            Run a workflow\n"
          "  status         Show status of runs\n"
          "  stop           Stop a run\n"
          "  logs           Show logs of a run\n"
          "  artifacts      List or download artifacts of a run\n"
          "  tags           List, create or delete tags\n"
          # "  dashboard      Launch a dashboard\n"
          # "  app            Open a running application\n"
          "\n"
          "Other commands:\n"
          "  init           Authorize dstack to access the current GitHub repo\n"
          "  config          Configure the backend\n"
          "  secrets        Manage secrets\n"
          # "  restart        Restart a run\n"
          "  delete         Delete runs\n"
          "\n"
          "Options:\n"
          "  -h, --help     Show this help output, or the help for a specified command.\n"
          "  -v, --version  Show the version of the CLI.\n"
          "\n"
          "For documentation, visit https://docs.dstack.ai/cli\n"
          "\n"
          "✨ Support us by giving us as star on GitHub: https://github.com/dstackai/dstack"
          )


def main():
    parser = ArgumentParser(add_help=False)
    parser.add_argument("-v", "--version", action="version", version=f"{version}", help="Show program's version")
    parser.add_argument('-h', '--help', action='store_true', default=SUPPRESS,
                        help='Show this help message and exit')
    parser.set_defaults(func=default_func)

    subparsers = parser.add_subparsers()

    # app.register_parsers(subparsers)
    artifacts.register_parsers(subparsers)
    config.register_parsers(subparsers)
    init.register_parsers(subparsers)
    logs.register_parsers(subparsers)
    delete.register_parsers(subparsers)
    # restart.register_parsers(subparsers)
    run.register_parsers(subparsers)
    secrets.register_parsers(subparsers)
    status.register_parsers(subparsers)
    stop.register_parsers(subparsers)
    tags.register_parsers(subparsers)
    dashboard.register_parsers(subparsers)

    if len(sys.argv) < 2:
        parser.print_help()
        exit(1)

    args, unknown = parser.parse_known_args()
    args.unknown = unknown
    args.func(args)


if __name__ == '__main__':
    main()
