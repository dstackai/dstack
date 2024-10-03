from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.utils.common import pretty_date


def print_gateways_table(gateways: List[Gateway], verbose: bool = False):
    table = get_gateways_table(gateways, verbose=verbose)
    console.print(table)
    console.print()


def get_gateways_table(gateways: List[Gateway], verbose: bool = False) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("BACKEND")
    table.add_column("HOSTNAME", no_wrap=True)
    table.add_column("DOMAIN")
    table.add_column("DEFAULT")
    table.add_column("STATUS")
    if verbose:
        table.add_column("CREATED")
        table.add_column("ERROR")

    for gateway in gateways:
        renderables = [
            gateway.name,
            f"{gateway.backend.value} ({gateway.region})",
            gateway.hostname,
            gateway.wildcard_domain,
            "✓" if gateway.default else "",
            gateway.status,
        ]
        if verbose:
            renderables.append(pretty_date(gateway.created_at))
            renderables.append(gateway.status_message)
        table.add_row(*renderables)
    return table
