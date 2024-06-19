from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.common import pretty_date


def print_volumes_table(volumes: List[Volume], verbose: bool = False):
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("BACKEND")
    table.add_column("REGION")
    table.add_column("STATUS")
    table.add_column("CREATED")

    for volume in volumes:
        renderables = [
            volume.name,
            volume.configuration.backend,
            volume.configuration.region,
            volume.status,
            pretty_date(volume.created_at),
        ]
        table.add_row(*renderables)

    console.print(table)
    console.print()
