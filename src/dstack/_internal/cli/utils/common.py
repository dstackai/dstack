import logging
import os
from typing import Any, Dict, Union

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich.theme import Theme

from dstack._internal.cli.utils.rich import DstackRichHandler
from dstack._internal.core.errors import CLIError, DstackError

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


def configure_logging():
    dstack_logger = logging.getLogger("dstack")
    dstack_logger.setLevel(os.getenv("DSTACK_CLI_LOG_LEVEL", "INFO").upper())
    handler = DstackRichHandler(console=console)
    handler.setFormatter(logging.Formatter(fmt="%(message)s", datefmt="[%X]"))
    dstack_logger.addHandler(handler)


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
