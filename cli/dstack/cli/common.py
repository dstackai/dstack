from importlib.util import find_spec
from typing import List, Optional, Tuple

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from dstack.backend.base import Backend
from dstack.core.job import JobStatus
from dstack.core.request import RequestStatus
from dstack.core.run import RunHead
from dstack.utils.common import pretty_date

is_termios_available = find_spec("termios") is not None


console = Console()


def ask_choice(
    title: str,
    labels: List[str],
    values: List[str],
    selected_value: Optional[str],
    show_choices: Optional[bool] = None,
) -> str:
    if selected_value not in values:
        selected_value = None
    if is_termios_available:
        from simple_term_menu import TerminalMenu

        console.print(
            f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold] "
            "[gray46]Use arrows to move, type to filter[/gray46]"
        )
        try:
            cursor_index = values.index(selected_value) if selected_value else None
        except ValueError:
            cursor_index = None
        terminal_menu = TerminalMenu(
            menu_entries=labels,
            menu_cursor_style=["fg_red", "bold"],
            menu_highlight_style=["fg_red", "bold"],
            search_key=None,
            search_highlight_style=["fg_purple"],
            cursor_index=cursor_index,
            raise_error_on_interrupt=True,
        )
        chosen_menu_index = terminal_menu.show()
        chosen_menu_label = labels[chosen_menu_index].replace("[", "\\[")
        console.print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{chosen_menu_label}[/grey74]")
        return values[chosen_menu_index]
    else:
        if len(values) < 10 and show_choices is None or show_choices is True:
            return Prompt.ask(
                prompt=f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold]",
                choices=values,
                default=selected_value,
            )
        else:
            value = Prompt.ask(
                prompt=f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold]",
                default=selected_value,
            )
            if value in values:
                return value
            else:
                console.print(
                    f"[red]Please select one of the available options: \\[{', '.join(values)}][/red]"
                )
                return ask_choice(title, labels, values, selected_value, show_choices)


def generate_runs_table(runs_with_backends: List[Tuple[RunHead, List[Backend]]]):
    table = Table(box=None)
    table.add_column("RUN", style="bold", no_wrap=True)
    table.add_column("WORKFLOW", style="grey58", max_width=16)
    table.add_column("SUBMITTED", style="grey58", no_wrap=True)
    table.add_column("OWNER", style="grey58", no_wrap=True, max_width=16)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("TAG", style="bold yellow", no_wrap=True)
    table.add_column("BACKENDS", style="bold green", no_wrap=True)

    for run, backends in runs_with_backends:
        submitted_at = pretty_date(round(run.submitted_at / 1000))
        table.add_row(
            _status_color(run, run.run_name, True, False),
            _status_color(run, run.workflow_name or run.provider_name, False, False),
            _status_color(run, submitted_at, False, False),
            _status_color(run, run.local_repo_user_name or "", False, False),
            pretty_print_status(run),
            _status_color(run, run.tag_name or "", False, False),
            _status_color(run, ", ".join(b.name for b in backends), False, False),
        )
    return table


def print_runs(runs_with_backends: List[Tuple[RunHead, List[Backend]]]):
    table = generate_runs_table(runs_with_backends)
    console.print(table)


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


def _status_color(run: RunHead, val: str, run_column: bool, status_column: bool):
    if status_column and run.has_request_status(
        [RequestStatus.TERMINATED, RequestStatus.NO_CAPACITY]
    ):
        color = "dark_orange"
    else:
        color = _status_colors.get(run.status)
    return f"[{'bold ' if run_column else ''}{color}]{val}[/]" if color is not None else val
