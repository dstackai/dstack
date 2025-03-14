from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.utils.common import DateFormatter, pretty_date


def print_gateways_table(gateways: List[Gateway], verbose: bool = False):
    table = get_gateways_table(gateways, verbose=verbose)
    console.print(table)
    console.print()


def get_gateways_table(
    gateways: List[Gateway],
    verbose: bool = False,
    include_created: bool = False,
    format_date: DateFormatter = pretty_date,
) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("BACKEND")
    table.add_column("HOSTNAME", no_wrap=True)
    table.add_column("DOMAIN")
    table.add_column("DEFAULT")
    table.add_column("STATUS")
    if verbose or include_created:
        table.add_column("CREATED")
    if verbose:
        table.add_column("ERROR")

    for gateway in gateways:
        row = {
            "NAME": gateway.name,
            "BACKEND": f"{gateway.configuration.backend.value} ({gateway.configuration.region})",
            "HOSTNAME": gateway.hostname,
            "DOMAIN": gateway.wildcard_domain,
            "DEFAULT": "✓" if gateway.default else "",
            "STATUS": gateway.status,
            "CREATED": format_date(gateway.created_at),
            "ERROR": gateway.status_message,
        }
        add_row_from_dict(table, row)
    return table
