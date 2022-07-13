import json
import sys
from argparse import Namespace

import colorama
import requests

from dstack.cli import confirm
from dstack.config import get_config, ConfigurationError


def untag_func(args: Namespace):
    try:
        if args.force or confirm(
                f"Are you sure you want to remove the tag from the run?"):
            dstack_config = get_config()
            # TODO: Support non-default profiles
            profile = dstack_config.get_profile("default")
            headers = {
                "Content-Type": f"application/json; charset=utf-8"
            }
            if profile.token is not None:
                headers["Authorization"] = f"Bearer {profile.token}"
            data = {"run_name": args.run_name}
            response = requests.request(method="POST", url=f"{profile.server}/runs/untag",
                                        data=json.dumps(data).encode("utf-8"),
                                        headers=headers, verify=profile.verify)
            if response.status_code == 404:
                sys.exit(f"No run '{args.run_name_or_job_id}' is found")
            elif response.status_code != 200:
                response.raise_for_status()
            else:
                print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
        else:
            print(f"{colorama.Fore.RED}Cancelled{colorama.Fore.RESET}")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("untag", help="Untag a run")

    parser.add_argument('run_name', metavar='RUN', type=str)
    parser.add_argument("--force", "-f", help="Don't ask for confirmation", action="store_true")

    parser.set_defaults(func=untag_func)
