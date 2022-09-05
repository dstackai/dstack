import json
import sys
from argparse import Namespace

from rich import print
import requests


def default_restart_workflow(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        headers = {
            "Content-Type": f"application/json; charset=utf-8"
        }
        if profile.token is not None:
            headers["Authorization"] = f"Bearer {profile.token}"

        data = {"run_name": args.run_name, "clear": args.clear is True}
        if args.workflow_name:
            data["workflow_name"] = args.workflow_name
        else:
            data["all"] = True
        response = requests.request(method="POST", url=f"{profile.server}/runs/workflows/restart",
                                    data=json.dumps(data).encode("utf-8"),
                                    headers=headers, verify=profile.verify)
        if response.status_code != 200:
            response.raise_for_status()
        print(f"[grey58]OK[/]")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("restart", help="Restart a run")

    parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run")
    parser.add_argument("-c", "--clear",
                        help="Clear logs and artifacts. By default, is false",
                        action="store_true")

    parser.set_defaults(func=default_restart_workflow)
