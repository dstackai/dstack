import json
import sys
from argparse import Namespace

import colorama
import requests
from dstack.cli.common import get_jobs

from dstack.cli.logs import logs_func
from dstack.config import get_config, ConfigurationError


def restart_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        headers = {
            "Content-Type": f"application/json; charset=utf-8"
        }
        if profile.token is not None:
            headers["Authorization"] = f"Bearer {profile.token}"

            if args.workflow_name is not None:
                jobs = list(
                    filter(lambda j: j["workflow_name"] == args.workflow_name, get_jobs(args.run_name, profile)))
                # TODO: Handle not found error
                for job in jobs:
                    # TODO: Do it in batch
                    # TODO: Do it in the right order
                    data = {"job_id": job["job_id"], "clear": args.clear is True}
                    response = requests.request(method="POST", url=f"{profile.server}/jobs/restart",
                                                data=json.dumps(data).encode("utf-8"),
                                                headers=headers, verify=profile.verify)
                    if response.status_code != 200:
                        response.raise_for_status()
            else:
                data = {"run_name": args.run_name, "clear": args.clear is True}
                response = requests.request(method="POST", url=f"{profile.server}/runs/restart",
                                            data=json.dumps(data).encode("utf-8"),
                                            headers=headers, verify=profile.verify)
                if response.status_code != 200:
                    response.raise_for_status()
            print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("restart", help="Restart a run")

    parser.add_argument("run_name", metavar="RUN", type=str)
    parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?")
    parser.add_argument("--clear", "-c",
                        help="Clear logs and artifacts. By default, is false",
                        action="store_true")

    parser.set_defaults(func=restart_func)
