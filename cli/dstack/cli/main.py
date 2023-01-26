import sys
from argparse import ArgumentParser, SUPPRESS, Namespace

# from dstack.cli import logs, run, stop, artifacts, ps, init, restart, rm, tags, config, secrets
from dstack.version import __version__ as version
from dstack.cli.handlers import cli_initialize
from rich import print


def default_func(_: Namespace):
    print("Usage: [bold]dstack [grey53][-h] [-v] [OPTIONS ...][/grey53] " +
          "COMMAND [grey53][ARGS ...][/grey53][/bold]\n"
          "\n"
          "Not sure where to start? Call [yellow bold]dstack config[/yellow bold], followed by [yellow bold]dstack init[/yellow bold].\n"
          "Define workflows within [bold].dstack/workflows[/bold] and run them via [bold]dstack run[/bold].\n"
          "\n"
          "Main commands:\n"
          "  [bold]dstack run WORKFLOW [grey53][-d] [-l] [-t TAG] [ARGS ...][/grey53][/bold]      Run a workflow\n"
          "  [bold]dstack ps [grey53][-a | RUN][/grey53][/bold]                                   Show [reset]run(s)[/reset] status\n"
          "  [bold]dstack logs [grey53][-a] [-s SINCE][/grey53] RUN[/bold]                        Show logs of a run\n"
          "  [bold]dstack stop [grey53][-x] [-y][/grey53] [grey53]([/grey53]RUN [grey53]|[/grey53] -a[grey53])[/grey53][/bold]                       Stop [reset]run(s)[/reset]\n"
          "  [bold]dstack artifacts list [grey53]([/grey53]RUN [grey53]|[/grey53] :TAG[grey53])[/grey53][/bold]                     List artifacts\n"
          "  [bold]dstack artifacts download [grey53]([/grey53]RUN [grey53]|[/grey53] :TAG[grey53])[/grey53][/bold]                 Download artifacts\n"
          "\n"
          "Other commands:\n"
          # "app            Open a running application\n"
          "  [bold]dstack config[/bold]                                          Configure the backend\n"
          "  [bold]dstack init [grey53][-t OAUTH_TOKEN | -i SSH_PRIVATE_KEY][/grey53][/bold]      " +
          "Initialize the repo\n"
          "  [bold]dstack tags list[/bold]                                       List tags\n"
          "  [bold]dstack tags add TAG [grey53]([/grey53]-r RUN [grey53]|[/grey53] -a PATH [grey53]...)[/grey53][/bold]             Add a tag\n"
          "  [bold]dstack tags delete [grey53][-y][/grey53] TAG[/bold]                            Delete a tag\n"
          "  [bold]dstack rm [grey53][-y][/grey53] [grey53]([/grey53]RUN [grey53]|[/grey53] -a[grey53])[/grey53][/bold]                              Delete [reset]run(s)[/reset]\n"
          "  [bold]dstack secrets add [grey53][-y][/grey53] NAME [grey53][VALUE][/grey53][/bold]                   Add a secret\n"
          "  [bold]dstack secrets list[/bold]                                    List secrets\n"
          "  [bold]dstack secrets delete NAME[/bold]                             Delete a secret\n"
          # "restart        Restart a run\n"
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

    cli_initialize(parser=subparsers)

    if len(sys.argv) < 2:
        default_func(Namespace())
        exit(1)
    args, unknown = parser.parse_known_args()
    args.unknown = unknown
    args.func(args)


if __name__ == '__main__':
    main()
