import io
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from rich.console import Console
from rich.file_proxy import FileProxy
from rich.prompt import Confirm
from rich.table import Table
from rich.theme import Theme

from dstack._internal import settings
from dstack._internal.cli.utils.rich import DstackRichHandler
from dstack._internal.core.errors import CLIError, DstackError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.utils.common import get_dstack_dir, parse_since

_colors = {
    "secondary": "grey58",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "code": "bold sea_green3",
}

console = Console(theme=Theme(_colors))


class _LiveAwareStderr:
    """
    Resolves `sys.stderr` on each call. `Console(stderr=True)` unwraps the proxy that
    `rich.live.Live` installs on `sys.stderr`, so its output would bypass an active
    `console.status()` or live table and break the render.
    """

    @property
    def encoding(self) -> str:
        return getattr(sys.stderr, "encoding", None) or "utf-8"

    def write(self, text: str) -> int:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()

    def isatty(self) -> bool:
        return sys.stderr.isatty()

    def fileno(self) -> int:
        if isinstance(sys.stderr, FileProxy):
            # Without a std stream fileno, rich on legacy Windows consoles renders ANSI
            # in one write instead of a write and flush per styled segment, each of
            # which `FileProxy` would print on a separate line.
            raise io.UnsupportedOperation("fileno")
        return sys.stderr.fileno()


error_console = Console(theme=Theme(_colors), file=_LiveAwareStderr())  # type: ignore[arg-type]
"""Logs, errors, and warnings. Keeps stdout for command output, e.g., `--json`."""


LIVE_TABLE_REFRESH_RATE_PER_SEC = 1
LIVE_TABLE_PROVISION_INTERVAL_SECS = 2
NO_OFFERS_WARNING = (
    "[warning]"
    "No matching instance offers available. Possible reasons:"
    " [link]https://dstack.ai/docs/guides/troubleshooting/#no-offers[/link]"
    "[/]\n"
)
NO_FLEETS_WARNING = (
    "[error]"
    "The project has no fleets. Create one before submitting a run.\n"
    "See [link]https://dstack.ai/docs/guides/troubleshooting/#no-fleets[/link]"
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

    stderr_handler = DstackRichHandler(console=error_console)
    stderr_handler.setFormatter(logging.Formatter(fmt="%(message)s", datefmt="[%X]"))
    stderr_handler.setLevel(settings.CLI_LOG_LEVEL)
    dstack_logger.addHandler(stderr_handler)

    log_file = get_dstack_dir() / "logs" / "cli" / "latest.log"
    try:
        log_file = _get_cli_log_file()
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        file_handler.setLevel(settings.CLI_FILE_LOG_LEVEL)
        dstack_logger.addHandler(file_handler)
    except PermissionError:
        error_console.print(
            f"[warning]Couldn't write to {log_file} due to a permissions problem.[/]"
        )

    # the logger allows all messages, filtering is done by the handlers
    dstack_logger.setLevel(logging.DEBUG)


def confirm_ask(prompt, **kwargs) -> bool:
    kwargs["console"] = console
    return Confirm.ask(prompt=prompt, **kwargs)


def add_row_from_dict(table: Table, data: dict[str, Any], **kwargs):
    """Maps dict keys to table columns. `data` key is the column name. Missing keys are ignored."""
    row = []
    for col in table.columns:
        row.append(data.get(str(col.header), ""))
    table.add_row(*row, **kwargs)


def warn(message: str):
    if not message.endswith("\n"):
        # Additional blank line for better visibility if there are more than one warning
        message = f"{message}\n"
    error_console.print(f"[warning][bold]{message}[/]")


def get_start_time(since: Optional[str]) -> Optional[datetime]:
    if since is None:
        return None
    try:
        return parse_since(since)
    except ValueError as e:
        raise CLIError(e.args[0])


def resolve_url(url: str, timeout: float = 5.0) -> str:
    """
    Starts with http:// and follows redirects. Returns the final URL (including scheme).
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    try:
        response = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
        )
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Failed to resolve url {url}") from e
    return response.url


def format_entity_reference(name: str, project: str, current_project: str) -> str:
    if current_project == project:
        return name
    else:
        return f"{project}/{name}"


def format_instance_availability(v: InstanceAvailability) -> str:
    if v in (InstanceAvailability.UNKNOWN, InstanceAvailability.AVAILABLE):
        return ""
    return v.value.replace("_", " ").lower()


def format_backend(backend: Optional[BackendType], region: Optional[str]) -> str:
    if backend is None:
        return "-"
    backend_str = backend.value
    if backend == BackendType.REMOTE:
        backend_str = "ssh"
    if region:
        backend_str += f" ({region})"
    return backend_str
