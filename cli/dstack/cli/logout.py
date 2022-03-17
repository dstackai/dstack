from argparse import Namespace

import colorama

from dstack.config import from_yaml_file, _get_config_path


def logout_func(_: Namespace):
    config_path = _get_config_path(None)
    if config_path.exists():
        config_path.unlink()
    print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("logout", help="Log out")

    parser.set_defaults(func=logout_func)
