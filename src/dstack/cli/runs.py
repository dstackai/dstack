import os
import sys
from argparse import Namespace
from itertools import groupby

from git import InvalidGitRepositoryError
from rich import box
from rich.console import Console
from rich.table import Table

from dstack.backend import load_backend, Backend, Run
from dstack.cli.common import colored, pretty_date, load_repo_data
from dstack.config import ConfigError


def runs_func(args: Namespace):
    try:
        backend = load_backend()
        print_runs(args, backend)
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")


def pretty_print_status(run: Run) -> str:
    status = run.status.name.upper()
    availability_issues = run.availability_issues
    if availability_issues:
        return "No capacity"
    if status == "SUBMITTED":
        return "Provisioning..."
    if status == "QUEUED":
        return "Provisioning..."
    if status == "RUNNING":
        return "Running..."
    if status == "DONE":
        return "Done"
    if status == "FAILED":
        return "Failed"
    if status == "STOPPING":
        return "Stopping..."
    if status == "ABORTING":
        return "Aborting..."
    if status == "STOPPED":
        return "Stopped"
    if status == "ABORTED":
        return "Aborted"
    if status == "REQUESTED":
        return "Provisioning..."


def print_runs(args: Namespace, backend: Backend):
    repo_user_name, repo_name, _, _, _ = load_repo_data()
    runs = backend.get_runs(repo_user_name, repo_name, args.run_name)
    if not args.all:
        unfinished = any(run.status.is_unfinished() for run in runs)
        if unfinished:
            runs = list(filter(lambda r: r.status.is_unfinished(), runs))
        else:
            runs = runs[:1]
    runs = reversed(runs)

    runs_by_name = [(run_name, list(run)) for run_name, run in
                    groupby(runs, lambda run: run.run_name)]
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

    for run_name, runs in runs_by_name:
        for i in range(len(runs)):
            run = runs[i]
            submitted_at = pretty_date(round(run.submitted_at / 1000))
            status = run.status.name
            tag_name = run.tag_name
            run_name = run.run_name
            # TODO: Handle availability issues
            table.add_row(colored(status, run_name),
                          run.workflow_name,
                          run.provider_name,
                          colored(status, pretty_print_status(run)),
                          __job_apps(run.apps, status),
                          '\n'.join(run.artifacts or []),
                          submitted_at,
                          f"{tag_name}" if tag_name else "")
    console.print(table)


def get_workflow_runs(args: Namespace, backend: Backend):
    workflows_by_id = {}
    repo_user_name, repo_name, _, _, _ = load_repo_data()
    job_heads = backend.get_job_heads(repo_user_name, repo_name, args.run_name)
    unfinished = False
    for job_head in job_heads:
        if job_head.status.is_unfinished():
            unfinished = True
        workflow_id = ','.join([job_head.run_name, job_head.workflow_name or ''])
        if workflow_id not in workflows_by_id:
            workflow = {
                "run_name": job_head.run_name,
                "workflow_name": job_head.workflow_name,
                "provider_name": job_head.provider_name,
                "artifacts": job_head.artifacts or [],
                "status": job_head.status,
                "submitted_at": job_head.submitted_at,
                "tag_name": job_head.tag_name
            }
            workflows_by_id[workflow_id] = workflow
        else:
            workflow = workflows_by_id[workflow_id]
            workflow["submitted_at"] = min(workflow["submitted_at"], job_head.submitted_at)
            if job_head.artifacts:
                workflow["artifacts"].extend(job_head.artifacts)
            if job_head.status.is_unfinished():
                # TODO: implement max(status1, status2)
                workflow["status"] = job_head.status

    workflows = list(workflows_by_id.values())
    workflows = sorted(workflows, key=lambda j: j["submitted_at"], reverse=True)
    if not args.all:
        if unfinished:
            workflows = list(filter(lambda w: w["status"].is_unfinished(), workflows))
    for workflow in workflows:
        workflow["status"] = workflow["status"].value
    return reversed(workflows)


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


def __job_apps(apps, status):
    if status == "RUNNING" and apps is not None and len(apps) > 0:
        return "✔"
        # return "\n".join(map(lambda app: app.get("app_name"), apps))
    else:
        return ""


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("runs", help="Lists runs")

    parser.add_argument("run_name", metavar="RUN", type=str, nargs="?", help="A name of a run")
    parser.add_argument("-a", "--all",
                        help="Show recent runs. By default, it shows only active runs, or the last finished.",
                        action="store_true")

    parser.set_defaults(func=runs_func)
