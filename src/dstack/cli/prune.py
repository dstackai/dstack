import json
import os
import sys
from argparse import Namespace

import colorama
from git import InvalidGitRepositoryError
from requests import request

from dstack.cli import confirm
from dstack.cli.common import load_repo_data
from dstack.config import get_config, ConfigurationError


def prune_func(args: Namespace):
    try:
        dstack_config = get_config()
        repo_url, _, _, _ = load_repo_data()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        if args.force or confirm(
                f"WARNING! This will permanently delete all untagged finished runs.\n\n"
                f"Are you sure you want to continue?"):
            headers = {
                "Content-Type": f"application/json; charset=utf-8"
            }
            if profile.token is not None:
                headers["Authorization"] = f"Bearer {profile.token}"
            data = {
                "repo_url": repo_url
            }
            data_bytes = json.dumps(data).encode("utf-8")
            response = request(method="POST", url=f"{profile.server}/runs/prune", data=data_bytes, headers=headers,
                               verify=profile.verify)
            if response.status_code == 200:
                print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
            elif response.status_code == 400:
                print(response.json()["message"])
            else:
                response.raise_for_status()
        else:
            print(f"{colorama.Fore.RED}Cancelled{colorama.Fore.RESET}")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("prune", help="Delete all untagged runs")
    parser.add_argument("--force", "-f", help="Don't ask for confirmation", action="store_true")

    parser.set_defaults(func=prune_func)
