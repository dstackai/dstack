import itertools
from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.utils.common import pretty_date


def print_gateways_table(gateways: List[Gateway], verbose: bool = False):
    table = Table(box=None)
    table.add_column("BACKEND")
    table.add_column("REGION")
    table.add_column("NAME")
    table.add_column("ADDRESS")
    table.add_column("DOMAIN")
    table.add_column("DEFAULT")
    if verbose:
        table.add_column("INSTANCE ID")
        table.add_column("CREATED")

    gateways = sorted(gateways, key=lambda g: g.backend)
    for backend, backend_gateways in itertools.groupby(gateways, key=lambda g: g.backend):
        for i, gateway in enumerate(backend_gateways):
            renderables = [
                backend.value if i == 0 else "",
                gateway.region,
                gateway.name,
                gateway.ip_address,
                gateway.wildcard_domain,
                "✓" if gateway.default else "",
            ]
            if verbose:
                renderables.append(gateway.instance_id)
                renderables.append(pretty_date(gateway.created_at))
            table.add_row(*renderables)
    console.print(table)
    console.print()
