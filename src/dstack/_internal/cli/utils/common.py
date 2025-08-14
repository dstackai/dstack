import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Union

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich.theme import Theme

from dstack._internal import settings
from dstack._internal.cli.utils.rich import DstackRichHandler
from dstack._internal.core.errors import CLIError, DstackError
from dstack._internal.utils.common import get_dstack_dir

_colors = {
    "secondary": "grey58",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "code": "bold sea_green3",
}

console = Console(theme=Theme(_colors))


LIVE_TABLE_REFRESH_RATE_PER_SEC = 1
LIVE_TABLE_PROVISION_INTERVAL_SECS = 2
NO_OFFERS_WARNING = (
    "[warning]"
    "No matching instance offers available. Possible reasons:"
    " https://dstack.ai/docs/guides/troubleshooting/#no-offers"
    "[/]\n"
)


def cli_error(e: DstackError) -> CLIError:
    return CLIError(*e.args)


def _get_cli_log_file() -> Path:
    """Get the CLI log file path, rotating the previous log if needed."""
    log_dir = get_dstack_dir() / "logs" / "cli"
    log_file = log_dir / "latest.log"

    if log_file.exists():
        file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime, tz=timezone.utc)
        current_date = datetime.now(timezone.utc).date()

        if file_mtime.date() < current_date:
            date_str = file_mtime.strftime("%Y-%m-%d")
            rotated_file = log_dir / f"{date_str}.log"

            counter = 1
            while rotated_file.exists():
                rotated_file = log_dir / f"{date_str}-{counter}.log"
                counter += 1

            log_file.rename(rotated_file)

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_file


def configure_logging():
    dstack_logger = logging.getLogger("dstack")
    dstack_logger.handlers.clear()

    log_file = _get_cli_log_file()

    stdout_handler = DstackRichHandler(console=console)
    stdout_handler.setFormatter(logging.Formatter(fmt="%(message)s", datefmt="[%X]"))
    stdout_handler.setLevel(settings.CLI_LOG_LEVEL)
    dstack_logger.addHandler(stdout_handler)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    file_handler.setLevel(settings.CLI_FILE_LOG_LEVEL)
    dstack_logger.addHandler(file_handler)

    # the logger allows all messages, filtering is done by the handlers
    dstack_logger.setLevel(logging.DEBUG)


def confirm_ask(prompt, **kwargs) -> bool:
    kwargs["console"] = console
    return Confirm.ask(prompt=prompt, **kwargs)


def add_row_from_dict(table: Table, data: Dict[Union[str, int], Any], **kwargs):
    """Maps dict keys to a table columns. `data` key is a column name or index. Missing keys are ignored."""
    row = []
    for i, col in enumerate(table.columns):
        # TODO(egor-s): clear header style
        if col.header in data:
            row.append(data[col.header])
        elif i in data:
            row.append(data[i])
        else:
            row.append("")
    table.add_row(*row, **kwargs)


def warn(message: str):
    if not message.endswith("\n"):
        # Additional blank line for better visibility if there are more than one warning
        message = f"{message}\n"
    console.print(f"[warning][bold]{message}[/]")
