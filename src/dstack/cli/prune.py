import json
import os
import sys
from argparse import Namespace

from rich import print
from git import InvalidGitRepositoryError
from requests import request

from rich.prompt import Confirm
from dstack.cli.common import load_repo_data
from dstack.config import get_config, ConfigurationError


def prune_func(args: Namespace):
    try:
        dstack_config = get_config()
        repo_url, _, _, _ = load_repo_data()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        if args.yes or Confirm.ask(
                f"[red]Delete all untagged finished runs?[/]"):
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
                print(f"[grey58]OK[/]")
            elif response.status_code == 400:
                print(response.json()["message"])
            else:
                response.raise_for_status()
        else:
            print(f"[red]Cancelled[/]")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("prune", help="Delete all untagged runs")
    parser.add_argument("--yes", "-y", help="Don't ask for confirmation", action="store_true")

    parser.set_defaults(func=prune_func)
