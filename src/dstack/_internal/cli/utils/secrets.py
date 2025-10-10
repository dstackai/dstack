from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.secrets import Secret


def print_secrets_table(secrets: List[Secret]) -> None:
    console.print(get_secrets_table(secrets))
    console.print()


def get_secrets_table(secrets: List[Secret]) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("VALUE")

    for secret in secrets:
        row = {
            "NAME": secret.name,
            "VALUE": secret.value or "*" * 6,
        }
        add_row_from_dict(table, row)
    return table
