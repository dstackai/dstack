import json
import sys
from argparse import Namespace

import colorama
import requests

from dstack.config import get_config, ConfigurationError


def tag_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        headers = {
            "Content-Type": f"application/json; charset=utf-8"
        }
        if profile.token is not None:
            headers["Authorization"] = f"Bearer {profile.token}"
        data = {"run_name": args.run_name}
        if args.name is not None:
            data["tag_name"] = args.name
        response = requests.request(method="POST", url=f"{profile.server}/runs/tag",
                                    data=json.dumps(data).encode("utf-8"),
                                    headers=headers, verify=profile.verify)
        if response.status_code == 404:
            sys.exit(f"No run '{args.run_name}' is found")
        elif response.status_code == 400:
            sys.exit(f"Tag already exists")
        elif response.status_code != 200:
            response.raise_for_status()
        else:
            print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("tag", help="Tag a run")

    parser.add_argument('run_name', metavar='RUN', type=str)
    parser.add_argument("--name", "-n", type=str,
                        help="The name of the tag. It's optional. "
                             "If not specified, the name of the tag will be the same as the name of the run.",
                        nargs="?")

    parser.set_defaults(func=tag_func)
