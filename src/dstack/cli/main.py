import sys
from argparse import ArgumentParser, SUPPRESS, Namespace

from dstack.cli import app, logs, run, stop, artifacts, status, init, \
    restart, delete, tags, config, dashboard, secrets
from dstack.version import __version__ as version
from rich import print


def default_func(_: Namespace):
    print("Usage: [bold]dstack [grey53][-h] [-v] [OPTIONS ...][/grey53] " +
          "COMMAND [grey53][ARGS ...][/grey53][/bold]\n"
          "\n"
          "Not sure where to start? Call [yellow bold]dstack config[/yellow bold], followed by [yellow bold]dstack init[/yellow bold].\n"
          "Define workflows in [bold].dstack/workflows.yaml[/bold] and run them via [bold]dstack run[/bold].\n"
          "\n"
          "Main commands:\n"
          "  [bold]dstack run WORKFLOW [grey53][-d] [-t TAG] [ARGS ...][/grey53][/bold]           Run a workflow\n"
          "  [bold]dstack ps [grey53][-a | RUN][/grey53][/bold]                                   Show [reset]run(s)[/reset] status\n"
          "  [bold]dstack stop [grey53][-x] [-y][/grey53] [grey53]([/grey53]RUN [grey53]|[/grey53] -a[grey53])[/grey53][/bold]                       Stop [reset]run(s)[/reset]\n"
          "  [bold]dstack logs [grey53][-a] [-s SINCE][/grey53] RUN[/bold]                        Show logs of a run\n"
          "  [bold]dstack artifacts list [grey53]([/grey53]RUN [grey53]|[/grey53] :TAG[grey53])[/grey53][/bold]                     List artifacts\n"
          "  [bold]dstack artifacts download [grey53]([/grey53]RUN [grey53]|[/grey53] :TAG[grey53])[/grey53][/bold]                 Download artifacts\n"
          "\n"
          "Other commands:\n"
          # "dashboard      Launch a dashboard\n"
          # "app            Open a running application\n"
          "  [bold]dstack init [grey53][-t GITHUB_TOKEN | -i SSH_PRIVATE_KEY][/grey53][/bold]     " +
          "Initialize the repo\n"
          "  [bold]dstack config[/bold]                                          Configure the backend\n"
          "  [bold]dstack tags add TAG [grey53]([/grey53]-r RUN [grey53]|[/grey53] -a PATH [grey53]...)[/grey53][/bold]             Add a tag\n"
          "  [bold]dstack tags delete [grey53][-y][/grey53] TAG[/bold]                            Delete a tag\n"
          "  [bold]dstack tags list[/bold]                                       List tags\n"
          "  [bold]dstack secrets add [grey53][-y][/grey53] NAME [grey53][VALUE][/grey53][/bold]                   Add a secret\n"
          "  [bold]dstack secrets list[/bold]                                    List secrets\n"
          "  [bold]dstack secrets delete NAME[/bold]                             Delete a secret\n"
          # "restart        Restart a run\n"
          "  [bold]dstack delete [grey53][-y][/grey53] [grey53]([/grey53]RUN [grey53]|[/grey53] -a[grey53])[/grey53][/bold]                          Delete [reset]run(s)[/reset]\n"
          "\n"
          "Global options:\n"
          "  [bold]-h[/bold], [bold]--help[/bold]                                             Show this help output\n"
          "  [bold]-v[/bold], [bold]--version[/bold]                                          Show dstack version\n"
          "\n"
          "For more details, check https://docs.dstack.ai/reference/cli\n"
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
        default_func(Namespace())
        exit(1)

    args, unknown = parser.parse_known_args()
    args.unknown = unknown
    args.func(args)


if __name__ == '__main__':
    main()
