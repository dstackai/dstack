import os
import sys
from argparse import Namespace
from itertools import groupby
from typing import List

from git import InvalidGitRepositoryError
from rich.console import Console
from rich.table import Table

from dstack.backend import load_backend, Backend, RunHead, RequestStatus
from dstack.cli.common import pretty_date
from dstack.config import ConfigError
from dstack.jobs import JobStatus
from dstack.repo import load_repo_data

_status_colors = {
    JobStatus.SUBMITTED: "yellow",
    JobStatus.DOWNLOADING: "yellow",
    JobStatus.RUNNING: "dark_sea_green4",
    JobStatus.UPLOADING: "dark_sea_green4",
    JobStatus.DONE: "gray74",
    JobStatus.FAILED: "red",
    JobStatus.STOPPED: "grey58",
    JobStatus.STOPPING: "yellow",
    JobStatus.ABORTING: "yellow",
    JobStatus.ABORTED: "grey58",
}


def _status_color(run: RunHead, val: str, run_column: bool, status_column: bool):
    if status_column and _has_request_status(run, [RequestStatus.TERMINATED, RequestStatus.NO_CAPACITY]):
        color = "dark_orange"
    else:
        color = _status_colors.get(run.status)
    return f"[{'bold ' if run_column else ''}{color}]{val}[/]" if color is not None else val


def _has_request_status(run, statuses: List[RequestStatus]):
    return run.status.is_unfinished() and any(filter(lambda s: s.status in statuses, run.request_heads or []))


def status_func(args: Namespace):
    try:
        backend = load_backend()
        print_runs(args, backend)
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")


def pretty_print_status(run: RunHead) -> str:
    status_color = _status_colors.get(run.status)
    status = run.status.value
    status = status[:1].upper() + status[1:]
    s = f"[{status_color}]{status}[/]"
    if _has_request_status(run, [RequestStatus.TERMINATED]):
        s += "\n[red]Request(s) terminated[/]"
    elif _has_request_status(run, [RequestStatus.NO_CAPACITY]):
        s += " \n[dark_orange]No capacity[/]"
    return s


def print_runs(args: Namespace, backend: Backend):
    repo_data = load_repo_data()
    job_heads = backend.list_job_heads(repo_data.repo_user_name, repo_data.repo_name, args.run_name)
    runs = backend.get_run_heads(repo_data.repo_user_name, repo_data.repo_name, job_heads)
    if not args.all:
        unfinished = any(run.status.is_unfinished() for run in runs)
        if unfinished:
            runs = list(filter(lambda r: r.status.is_unfinished(), runs))
        else:
            runs = runs[:1]
    runs = reversed(runs)

    runs_by_name = [(run_name, list(run)) for run_name, run in groupby(runs, lambda run: run.run_name)]
    console = Console()
    table = Table(box=None)
    table.add_column("RUN", style="bold", no_wrap=True)
    table.add_column("WORKFLOW", style="grey58", width=16)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("APPS", no_wrap=True)
    table.add_column("ARTIFACTS", style="grey58", width=18)
    table.add_column("SUBMITTED", style="grey58", no_wrap=True)
    table.add_column("TAG", style="bold yellow", no_wrap=True)

    for run_name, runs in runs_by_name:
        for i in range(len(runs)):
            run = runs[i]
            submitted_at = pretty_date(round(run.submitted_at / 1000))
            table.add_row(
                _status_color(run, run_name, True, False),
                _status_color(run, run.workflow_name or run.provider_name, False, False),
                pretty_print_status(run),
                _status_color(run, _app_heads(run.app_heads, run.status.name), False, False),
                _status_color(run, '\n'.join([a.artifact_path for a in run.artifact_heads or []]), False, False),
                _status_color(run, submitted_at, False, False),
                _status_color(run, f"{run.tag_name}" if run.tag_name else "", False, False))
    console.print(table)


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
    submitted_at_str = pretty_date(round(submitted_at / 1000)) if submitted_at is not None else ""
    return duration_str, submitted_at_str


def _app_heads(apps, status):
    if status == "RUNNING" and apps:
        return "\n".join(map(lambda app: app.app_name, apps))
    else:
        return ""


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("ps", help="List runs")

    parser.add_argument("run_name", metavar="RUN", type=str, nargs="?", help="A name of a run")
    parser.add_argument("-a", "--all",
                        help="Show status for all runs. "
                             "By default, it shows only status for unfinished runs, or the last finished.",
                        action="store_true")

    parser.set_defaults(func=status_func)
