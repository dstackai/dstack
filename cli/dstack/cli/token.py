import sys
from argparse import Namespace

from dstack.config import from_yaml_file, _get_config_path


def token_func(_: Namespace):
    dstack_config = from_yaml_file(_get_config_path(None))
    # TODO: Support non-default profiles
    profile = dstack_config.get_profile("default")
    if profile is None or profile.token is None:
        sys.exit("Call 'dstack config' first")
    else:
        print(profile.token)


# TODO: Add --reset argument
def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("token", help="Show the personal access token")

    parser.set_defaults(func=token_func)
