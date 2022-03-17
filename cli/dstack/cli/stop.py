import json
import sys
from argparse import Namespace

import colorama
import requests

from dstack.config import get_config, ConfigurationError


def default_stop_workflow(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        headers = {
            "Content-Type": f"application/json; charset=utf-8"
        }
        if profile.token is not None:
            headers["Authorization"] = f"Bearer {profile.token}"
        data = {"job_id": args.run_name_or_job_id}
        if args.abort is True:
            data["abort"] = True
        response = requests.request(method="POST", url=f"{profile.server}/jobs/stop",
                                    data=json.dumps(data).encode("utf-8"),
                                    headers=headers, verify=profile.verify)
        if response.status_code == 404:
            data = {"run_name": args.run_name_or_job_id}
            if args.abort is True:
                data["abort"] = True
            response = requests.request(method="POST", url=f"{profile.server}/runs/stop",
                                        data=json.dumps(data).encode("utf-8"),
                                        headers=headers, verify=profile.verify)
            if response.status_code == 404:
                sys.exit(f"No run or job '{args.run_name_or_job_id}' is found")
            elif response.status_code != 200:
                response.raise_for_status()
            else:
                print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
        elif response.status_code != 200:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("stop", help="Stop a run or job")

    parser.add_argument('run_name_or_job_id', metavar='(RUN | JOB)', type=str)
    parser.add_argument("-a", "--abort", help="Abort a run or job, i.e. don't upload artifacts", dest="abort",
                        action="store_true")

    parser.set_defaults(func=default_stop_workflow)
