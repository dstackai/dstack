import os
import sys
from argparse import Namespace
from itertools import groupby

import colorama
from git import InvalidGitRepositoryError
from requests import request
from tabulate import tabulate

from dstack.cli.common import colored, headers_and_params, pretty_date, short_artifact_path
from dstack.config import get_config, ConfigurationError


def runs_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        print_runs(profile, args)
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")


def print_runs(profile, args):
    runs = get_runs_v2(args, profile)
    runs_by_name = [(run_name, list(run)) for run_name, run in groupby(runs, lambda run: run["run_name"])]
    table_headers = [
        f"{colorama.Fore.LIGHTMAGENTA_EX}RUN{colorama.Fore.RESET}",
        f"{colorama.Fore.LIGHTMAGENTA_EX}WORKFLOW{colorama.Fore.RESET}",
        # f"{colorama.Fore.LIGHTMAGENTA_EX}REPO{colorama.Fore.RESET}",
        f"{colorama.Fore.LIGHTMAGENTA_EX}STATUS{colorama.Fore.RESET}",
        f"{colorama.Fore.LIGHTMAGENTA_EX}SUBMITTED{colorama.Fore.RESET}",
        # f"{colorama.Fore.LIGHTMAGENTA_EX}PORTS{colorama.Fore.RESET}",
        f"{colorama.Fore.LIGHTMAGENTA_EX}ARTIFACTS{colorama.Fore.RESET}",
        f"{colorama.Fore.LIGHTMAGENTA_EX}TAG{colorama.Fore.RESET}",
    ]
    table_rows = []
    for run_name, workflows in runs_by_name:
        for i in range(len(workflows)):
            workflow = workflows[i]
            workflow_status = workflow["status"].upper()
            _, submitted_at = pretty_duration_and_submitted_at(workflow.get("submitted_at"))
            status = workflow["status"].upper()
            table_rows.append([
                colored(workflow_status, workflow["run_name"]) if i == 0 else "",
                colored(status, workflow["workflow_name"]),
                # colored(status, pretty_repo_url(workflow["repo_url"])),
                colored(status, status),
                colored(status, submitted_at),
                # colored(workflow_status, "<none>"),
                colored(status, __job_artifacts(workflow["artifact_paths"])),
                colored(workflow_status,
                        "*" if workflow["tag_name"] == workflow["run_name"] else workflow[
                            "tag_name"] if workflow["tag_name"] else "<none>"),
            ])

    print(tabulate(table_rows, headers=table_headers, tablefmt="plain"))


def get_runs_v2(args, profile):
    headers, params = headers_and_params(profile, None, False)
    # del params["repo_url"]
    params["n"] = args.last
    response = request(method="GET", url=f"{profile.server}/runs/workflows/query", params=params, headers=headers,
                       verify=profile.verify)
    response.raise_for_status()
    # runs = sorted(response.json()["runs"], key=lambda job: job["updated_at"])
    runs = reversed(response.json()["runs"])
    return runs


def pretty_duration_and_submitted_at(submitted_at, started_at = None, finished_at = None):
    if started_at is not None and finished_at is not None:
        _finished_at_milli = round(finished_at / 1000)
        duration_milli = _finished_at_milli - round(started_at / 1000)
        hours, remainder = divmod(duration_milli, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = ""
        if int(hours) > 0:
            duration_str += "{} hours".format(int(hours))
        if int(minutes) > 0:
            if int(hours) > 0:
                duration_str += " "
            duration_str += "{} mins".format(int(minutes))
        if int(hours) == 0 and int(minutes) == 0:
            duration_str = "{} secs".format(int(seconds))
    else:
        duration_str = "<none>"
    submitted_at_str = pretty_date(round(submitted_at / 1000)) if submitted_at is not None else "<none>"
    return duration_str, submitted_at_str


def __job_artifacts(paths):
    if paths is not None and len(paths) > 0:
        return "\n".join(map(lambda path: short_artifact_path(path), paths))
    else:
        return "<none>"


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("runs", help="Lists runs")

    parser.add_argument("-n", "--last", help="Show the specified number of the most recent runs. By default, it's "
                                             "10.",
                        type=int, default=10)

    parser.set_defaults(func=runs_func)
