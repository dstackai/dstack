import os
import sys
from argparse import Namespace
from itertools import groupby

from git import InvalidGitRepositoryError
from requests import request
from rich import box
from rich.console import Console
from rich.table import Table

from dstack.cli.common import colored, headers_and_params, pretty_date, short_artifact_path, pretty_print_status
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
    console = Console()
    table = Table(box=box.SQUARE)
    table.add_column("Run", style="bold", no_wrap=True)
    table.add_column("Workflow", style="grey58", width=12)
    table.add_column("Provider", style="grey58", width=12)
    table.add_column("Status", no_wrap=True)
    table.add_column("App", justify="center", style="green", no_wrap=True)
    table.add_column("Artifacts", style="grey58", width=12)
    table.add_column("Submitted", style="grey58", no_wrap=True)
    table.add_column("Tag", style="bold yellow", no_wrap=True)

    for run_name, workflows in runs_by_name:
        for i in range(len(workflows)):
            workflow = workflows[i]
            _, submitted_at = pretty_duration_and_submitted_at(workflow.get("submitted_at"))
            status = workflow["status"].upper()
            tag_name = workflow.get("tag_name")
            run_name = workflow['run_name']
            # TODO: Handle availability issues
            table.add_row(colored(status, run_name),
                          workflow.get("workflow_name"),
                          workflow.get("provider_name"),
                          colored(status, pretty_print_status(workflow)),
                          __job_apps(workflow.get("apps"), status),
                          __job_artifacts(workflow["artifact_paths"]),
                          submitted_at,
                          f"{tag_name}" if tag_name else "")
    console.print(table)


def get_runs_v2(args, profile):
    headers, params = headers_and_params(profile, args.run_name, False)
    # del params["repo_url"]
    if args.all:
        params["n"] = 50
    response = request(method="GET", url=f"{profile.server}/runs/workflows/query", params=params, headers=headers,
                       verify=profile.verify)
    response.raise_for_status()
    # runs = sorted(response.json()["runs"], key=lambda job: job["updated_at"])
    runs = reversed(response.json()["runs"])
    return runs


def pretty_duration_and_submitted_at(submitted_at, started_at=None, finished_at=None):
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


def __job_apps(apps, status):
    if status == "RUNNING" and apps is not None and len(apps) > 0:
        return "✔"
        # return "\n".join(map(lambda app: app.get("app_name"), apps))
    else:
        return ""


def __job_artifacts(paths):
    if paths is not None and len(paths) > 0:
        return "\n".join(map(lambda path: short_artifact_path(path), paths))
    else:
        return ""


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("runs", help="Lists runs")

    parser.add_argument("run_name", metavar="RUN", type=str, nargs="?", help="A name of a run")
    parser.add_argument("-a", "--all",
                        help="Show recent runs. By default, it shows only active runs, or the last finished.",
                        action="store_true")

    parser.set_defaults(func=runs_func)
