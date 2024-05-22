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
    table.add_column("NAME", no_wrap=True)
    table.add_column("HOSTNAME", no_wrap=True)
    table.add_column("DOMAIN")
    table.add_column("DEFAULT")
    table.add_column("STATUS")
    if verbose:
        table.add_column("ERROR")
        table.add_column("CREATED")
        table.add_column("INSTANCE_ID")

    gateways = sorted(gateways, key=lambda g: g.backend)
    for backend, backend_gateways in itertools.groupby(gateways, key=lambda g: g.backend):
        for i, gateway in enumerate(backend_gateways):
            renderables = [
                backend.value if i == 0 else "",
                gateway.region,
                gateway.name,
                gateway.hostname,
                gateway.wildcard_domain,
                "✓" if gateway.default else "",
                gateway.status,
            ]
            if verbose:
                renderables.append(gateway.status_message)
                renderables.append(pretty_date(gateway.created_at))
                renderables.append(gateway.instance_id)
            table.add_row(*renderables)
    console.print(table)
    console.print()
