import argparse
from typing import List

from rich.console import Console
from rich.table import Table

from dstack._internal.cli.errors import CLIError
from dstack._internal.core.error import RepoNotInitializedError
from dstack._internal.core.job import JobErrorCode, JobStatus
from dstack._internal.core.request import RequestStatus
from dstack._internal.core.run import RunHead
from dstack._internal.utils.common import pretty_date
from dstack.api.hub.errors import HubClientError

console = Console()


def print_runs(runs: List[RunHead], include_configuration: bool = False, verbose: bool = False):
    table = generate_runs_table(runs, include_configuration=include_configuration, verbose=verbose)
    console.print(table)


def generate_runs_table(
    runs: List[RunHead], include_configuration: bool = False, verbose: bool = False
) -> Table:
    table = Table(box=None)
    table.add_column("RUN", style="bold", no_wrap=True)
    if include_configuration:
        table.add_column("CONFIGURATION", style="grey58")
    table.add_column("USER", style="grey58", no_wrap=True, max_width=16)
    table.add_column("INSTANCE", no_wrap=True)
    table.add_column("SPOT", no_wrap=True)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("SUBMITTED", style="grey58", no_wrap=True)
    if verbose:
        table.add_column("TAG", style="bold yellow", no_wrap=True)
        table.add_column("ERROR", no_wrap=True)

    for run in runs:
        submitted_at = pretty_date(round(run.submitted_at / 1000))
        row = [_status_color(run, run.run_name, True, False)]
        if include_configuration:
            row.append(_status_color(run, run.configuration_path, False, False))
        row.extend(
            [
                _status_color(run, run.hub_user_name or "", False, False),
                _pretty_print_instance_type(run),
                _pretty_print_spot(run),
                _pretty_print_status(run),
                _status_color(run, submitted_at, False, False),
            ]
        )
        if verbose:
            row += [
                _status_color(run, run.tag_name or "", False, False),
                _pretty_print_error_code(run),
            ]
        table.add_row(*row)
    return table


_status_colors = {
    JobStatus.SUBMITTED: "yellow",
    JobStatus.PENDING: "yellow",
    JobStatus.DOWNLOADING: "yellow",
    JobStatus.BUILDING: "yellow",
    JobStatus.RUNNING: "dark_sea_green4",
    JobStatus.UPLOADING: "dark_sea_green4",
    JobStatus.DONE: "grey74",
    JobStatus.FAILED: "red",
    JobStatus.STOPPED: "grey58",
    JobStatus.STOPPING: "yellow",
    JobStatus.ABORTING: "yellow",
    JobStatus.ABORTED: "grey58",
}


def _pretty_print_status(run: RunHead) -> str:
    status_color = _status_colors.get(run.status)
    status = run.status.value.capitalize()
    s = f"[{status_color}]{status}[/]"
    if run.status.is_unfinished() and run.status != JobStatus.PENDING:
        if run.has_request_status([RequestStatus.TERMINATED]):
            s += "\n[red]Request(s) terminated[/]"
        elif run.has_request_status([RequestStatus.NO_CAPACITY]):
            s += " \n[dark_orange]No capacity[/]"
    return s


def _status_color(run: RunHead, val: str, run_column: bool, status_column: bool):
    if status_column and run.has_request_status(
        [RequestStatus.TERMINATED, RequestStatus.NO_CAPACITY]
    ):
        color = "dark_orange"
    else:
        color = _status_colors.get(run.status)
    return f"[{'bold ' if run_column else ''}{color}]{val}[/]" if color is not None else val


def _pretty_print_error_code(run: RunHead) -> str:
    if run.status != JobStatus.FAILED:
        return ""
    for job_head in run.job_heads:
        if job_head.error_code is not None:
            if job_head.error_code == JobErrorCode.CONTAINER_EXITED_WITH_ERROR:
                return f"[red]Exit code: {job_head.container_exit_code}[/]"
            else:
                return f"[red]{job_head.error_code.pretty_repr()}[/]"
    return ""


def _pretty_print_spot(run: RunHead) -> str:
    spot = "yes" if run.job_heads[0].instance_spot_type == "spot" else "no"
    return _status_color(run, spot, False, False)


def _pretty_print_instance_type(run: RunHead) -> str:
    instances = [
        _status_color(run, job.instance_type, False, False)
        for job in run.job_heads
        if job.instance_type
    ] or [_status_color(run, "-", False, False)]
    return "\n".join(instances)


def check_init(func):
    def decorator(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except RepoNotInitializedError as e:
            command = "dstack init"
            if e.project_name is not None:
                command += f" --project {e.project_name}"
            console.print(f"The repository is not initialized. Call `{command}` first.")
            exit(1)

    return decorator


def check_cli_errors(func):
    def decorator(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except (CLIError, HubClientError) as e:
            console.print(e.message)
            exit(1)

    return decorator


def add_project_argument(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--project",
        type=str,
        help="The name of the project",
        default=None,
    )
