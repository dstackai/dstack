import os
import sys
from argparse import Namespace

from git import InvalidGitRepositoryError

from dstack.cli.common import print_runs
from dstack.config import get_config, ConfigurationError


def runs_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        print_runs(profile, args)
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("runs", help="Lists runs")

    parser.add_argument("-a", "--all", help="Show all runs. By default, shows all unfinished or the last finished.",
                        action="store_true")

    parser.set_defaults(func=runs_func)
