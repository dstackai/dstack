from rich.console import Console
from rich.theme import Theme

from dstack._internal.core.errors import CLIError, DstackError

colors = {
    "secondary": "grey58",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "code": "bold sea_green3",
}

console = Console(theme=Theme(colors))


def cli_error(e: DstackError) -> CLIError:
    return CLIError(*e.args)
