from typing import List

from argparse import Namespace
from rich.console import Console
from rich.table import Table
from itertools import groupby

from dstack.cli.commands import BasicCommand
from dstack.core.error import check_config, check_git
from dstack.core.job import JobStatus
from dstack.api.run import list_runs
from dstack.core.request import RequestStatus
from dstack.core.run import RunHead
from dstack.api.backend import list_backends
from dstack.utils.common import pretty_date


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
    if status_column and run.has_request_status(
        [RequestStatus.TERMINATED, RequestStatus.NO_CAPACITY]
    ):
        color = "dark_orange"
    else:
        color = _status_colors.get(run.status)
    return f"[{'bold ' if run_column else ''}{color}]{val}[/]" if color is not None else val


def pretty_print_status(run: RunHead) -> str:
    status_color = _status_colors.get(run.status)
    status = run.status.value
    status = status[:1].upper() + status[1:]
    s = f"[{status_color}]{status}[/]"
    if run.has_request_status([RequestStatus.TERMINATED]):
        s += "\n[red]Request(s) terminated[/]"
    elif run.has_request_status([RequestStatus.NO_CAPACITY]):
        s += " \n[dark_orange]No capacity[/]"
    return s


def print_runs(runs: List[RunHead]):
    runs_by_name = [
        (run_name, list(run)) for run_name, run in groupby(runs, lambda run: run.run_name)
    ]
    console = Console()
    table = Table(box=None)
    table.add_column("RUN", style="bold", no_wrap=True)
    table.add_column("WORKFLOW", style="grey58", max_width=16)
    table.add_column("SUBMITTED", style="grey58", no_wrap=True)
    table.add_column("OWNER", style="grey58", no_wrap=True, max_width=16)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("TAG", style="bold yellow", no_wrap=True)
    table.add_column("BACKEND", style="bold green", no_wrap=True, max_width=8)

    for run_name, runs in runs_by_name:
        for run in runs:
            submitted_at = pretty_date(round(run.submitted_at / 1000))
            table.add_row(
                _status_color(run, run_name, True, False),
                _status_color(run, run.workflow_name or run.provider_name, False, False),
                _status_color(run, submitted_at, False, False),
                _status_color(run, run.local_repo_user_name or "", False, False),
                pretty_print_status(run),
                _status_color(run, run.tag_name or "", False, False),
                _status_color(run, run.backend_name or "???", False, False),
            )
    console.print(table)


class PSCommand(BasicCommand):
    NAME = "ps"
    DESCRIPTION = "List runs"

    def __init__(self, parser):
        super(PSCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name", metavar="RUN", type=str, nargs="?", help="A name of a run"
        )
        self._parser.add_argument(
            "-a",
            "--all",
            help="Show status for all runs. "
            "By default, it shows only status for unfinished runs, or the last finished.",
            action="store_true",
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        print_runs(list_runs(list_backends(), args.run_name, args.all))
