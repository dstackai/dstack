import sys
from argparse import Namespace

from dstack.cli.common import print_runners
from dstack.config import get_config, ConfigurationError


def runners_func(_: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        print_runners(profile)
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("runners", help="Show runners")

    parser.set_defaults(func=runners_func)
