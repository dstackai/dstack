import json
import os
import sys
import webbrowser
from argparse import Namespace
from json import JSONDecodeError

import colorama
from git import InvalidGitRepositoryError
from requests import request

from dstack.cli.common import get_user_info, get_jobs, headers_and_params
from dstack.config import get_config, ConfigurationError


def get_runs_v2(args, profile):
    headers, params = headers_and_params(profile, args.run_name, False)
    # del params["repo_url"]
    response = request(method="GET", url=f"{profile.server}/runs/workflows/query", params=params, headers=headers,
                       verify=profile.verify)
    response.raise_for_status()
    # runs = sorted(response.json()["runs"], key=lambda job: job["updated_at"])
    runs = reversed(response.json()["runs"])
    return runs


def apps_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        workflows = get_runs_v2(args, profile)

        apps = []
        for workflow in filter(lambda w: not args.workflow_name or w.workflow_name == args.workflow_name, workflows):
            for app in workflow.get("apps") or []:
                apps.append(app)
        if len(apps) > 0:
            url = apps[0].get("url")
            if url:
                print(f"The application url is {url}")
                print("Opening it in the browser...")
                webbrowser.open(apps[0]["url"])
                print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
            else:
                sys.exit("Application is not initialized yet")
        else:
            sys.exit("No application is found")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("app", help="Open an app")

    parser.add_argument("run_name", metavar="RUN", type=str)
    parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?")
    parser.set_defaults(func=apps_func)
