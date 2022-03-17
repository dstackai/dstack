import json
import sys
from argparse import Namespace

import colorama
import requests

from dstack.cli.logs import logs_func
from dstack.config import get_config, ConfigurationError


# TODO: Make it work for runs too
def resume_func(args: Namespace):
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
        response = requests.request(method="POST", url=f"{profile.server}/jobs/resume",
                                    data=json.dumps(data).encode("utf-8"),
                                    headers=headers, verify=profile.verify)
        if response.status_code == 404:
            data = {"run_name": args.run_name_or_job_id}
            response = requests.request(method="POST", url=f"{profile.server}/runs/resume",
                                        data=json.dumps(data).encode("utf-8"),
                                        headers=headers, verify=profile.verify)
            if response.status_code == 404:
                sys.exit(f"No run or job '{args.run_name_or_job_id}' is found")
            elif response.status_code == 400 and response.json()["message"] == "run is not stopped":
                sys.exit(f"The run '{args.run_name_or_job_id}' is not stopped")
            elif response.status_code != 200:
                response.raise_for_status()
            else:
                if args.follow:
                    logs_func(Namespace(run_name_or_job_id=args.run_name_or_job_id, follow=True, since="0d"))
                else:
                    print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
        elif response.status_code == 400 and response.json()["message"] == "other jobs depend on it":
            sys.exit(f"The job cannot be resumed because other jobs depend on it")
        elif response.status_code == 400 and response.json()["message"] == "job is not stopped":
            sys.exit(f"The '{args.run_name_or_job_id}' job is not stopped")
        elif response.status_code != 200:
            response.raise_for_status()
        else:
            if args.follow:
                logs_func(Namespace(run_name_or_job_id=args.run_name_or_job_id, follow=True, since="0d"))
            else:
                print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("resume", help="Resume a stopped run or job")

    parser.add_argument('run_name_or_job_id', metavar='(RUN | JOB)', type=str)
    parser.add_argument("--follow", "-f",
                        help="Whether to continuously poll and print logs of the workflow. "
                             "By default, the command doesn't print logs. To exit from this "
                             "mode, use Control-C.", action="store_true")

    parser.set_defaults(func=resume_func)
