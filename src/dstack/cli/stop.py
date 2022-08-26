import os
import sys
from argparse import Namespace

from git import InvalidGitRepositoryError
from rich import print
from rich.prompt import Confirm

from dstack.backend import load_backend
from dstack.config import ConfigError
from dstack.repo import load_repo_data


def stop_func(args: Namespace):
    if (args.run_name and (args.yes or Confirm.ask(f"[red]Stop the run `{args.run_name}`?[/]"))) \
            or (args.all and (args.yes or Confirm.ask("[red]Stop all runs?[/]"))):
        try:
            repo_data = load_repo_data()
            backend = load_backend()
            backend.stop_jobs(repo_data.repo_user_name, repo_data.repo_name, args.run_name, args.abort)
            print(f"[grey58]OK[/]")
        except InvalidGitRepositoryError:
            sys.exit(f"{os.getcwd()} is not a Git repo")
        except ConfigError:
            sys.exit(f"Call 'dstack config' first")
    else:
        if not args.run_name and not args.all:
            sys.exit("Specify a run name or use --all to stop all workflows")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("stop", help="Stop runs")

    parser.add_argument("run_name", metavar="RUN", type=str, nargs="?", help="A name of a run")
    parser.add_argument("-a", "--all", help="All runs", dest="all", action="store_true")
    parser.add_argument("--abort", help="Don't wait for a graceful stop", dest="abort", action="store_true")
    parser.add_argument("--yes", "-y", help="Don't ask for confirmation", action="store_true")

    parser.set_defaults(func=stop_func)
