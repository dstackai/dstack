import logging
import os
from datetime import datetime
from typing import Optional

from rich.console import Console, ConsoleRenderable
from rich.logging import RichHandler
from rich.prompt import Confirm
from rich.theme import Theme
from rich.traceback import Traceback

from dstack._internal.core.errors import CLIError, DstackError

_colors = {
    "secondary": "grey58",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "code": "bold sea_green3",
}

console = Console(theme=Theme(_colors))


def cli_error(e: DstackError) -> CLIError:
    return CLIError(*e.args)


def configure_logging():
    dstack_logger = logging.getLogger("dstack")
    dstack_logger.setLevel(os.getenv("DSTACK_CLI_LOG_LEVEL", "WARNING").upper())
    handler = DstackRichHandler(console=console)
    handler.setFormatter(logging.Formatter(fmt="%(message)s", datefmt="[%X]"))
    dstack_logger.addHandler(handler)


class DstackRichHandler(RichHandler):
    def render(
        self,
        *,
        record: logging.LogRecord,
        traceback: Optional[Traceback],
        message_renderable: ConsoleRenderable,
    ) -> ConsoleRenderable:
        path = record.name  # the key difference from RichHandler
        level = self.get_level_text(record)
        time_format = None if self.formatter is None else self.formatter.datefmt
        log_time = datetime.fromtimestamp(record.created)

        log_renderable = self._log_render(
            self.console,
            [message_renderable] if not traceback else [message_renderable, traceback],
            log_time=log_time,
            time_format=time_format,
            level=level,
            path=path,
            line_no=record.lineno,
            link_path=record.pathname if self.enable_link_path else None,
        )
        return log_renderable


def confirm_ask(prompt, **kwargs) -> bool:
    kwargs["console"] = console
    return Confirm.ask(prompt=prompt, **kwargs)
