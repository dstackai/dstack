from typing import List

from rich.table import Table

from dstack._internal.cli.models.gateways import GatewayCommandOutput
from dstack._internal.cli.utils.common import add_row_from_dict, console, format_entity_reference
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.utils.common import DateFormatter, pretty_date


def print_gateways_table(gateways: List[Gateway], current_project: str, verbose: bool = False):
    table = get_gateways_table(gateways, current_project, verbose=verbose)
    console.print(table)
    console.print()


def print_gateways_json(gateways: List[Gateway], project: str) -> None:
    """Print gateways information in JSON format."""
    output = GatewayCommandOutput(
        project=project,
        gateways=gateways,
    )
    print(output.json())


def get_gateways_table(
    gateways: List[Gateway],
    current_project: str,
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
        name = format_entity_reference(
            gateway.name,
            # project_name == None means pre-0.20.20 server, which means no gateway exports support,
            # which means the gateway is from the current project
            gateway.project_name if gateway.project_name is not None else current_project,
            current_project,
        )
        row = {
            "NAME": name,
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
