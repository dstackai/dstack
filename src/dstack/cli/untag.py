import json
import sys
from argparse import Namespace

from rich import print
import requests

from rich.prompt import Confirm
from dstack.config import get_config, ConfigurationError


def untag_func(args: Namespace):
    try:
        if args.yes or Confirm.ask(f"Are you sure you want to remove the tag from the run?"):
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
                print(f"[grey58]OK[/]")
        else:
            print(f"[red]Cancelled[/]")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("untag", help="Untag a run")

    parser.add_argument('run_name', metavar='RUN', type=str, help="A name of a run")
    parser.add_argument("--yes", "-y", help="Don't ask for confirmation", action="store_true")

    parser.set_defaults(func=untag_func)
