from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.common import DateFormatter, pretty_date


def print_volumes_table(volumes: List[Volume], verbose: bool = False):
    table = get_volumes_table(volumes, verbose=verbose)
    console.print(table)
    console.print()


def get_volumes_table(
    volumes: List[Volume], verbose: bool = False, format_date: DateFormatter = pretty_date
) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("BACKEND")
    if verbose:
        table.add_column("REGION")
    table.add_column("STATUS")
    table.add_column("CREATED")
    if verbose:
        table.add_column("ERROR")

    for volume in volumes:
        if verbose:
            backend = f"{volume.configuration.backend.value}"
            region = f"{volume.configuration.region}"
            if (
                verbose
                and volume.provisioning_data is not None
                and volume.provisioning_data.availability_zone is not None
            ):
                region += f" ({volume.provisioning_data.availability_zone})"
        else:
            backend = f"{volume.configuration.backend.value} ({volume.configuration.region})"
            region = f"{volume.configuration.region}"
        renderables = [
            volume.name,
            backend,
        ]
        if verbose:
            renderables.append(region)
        renderables += [
            volume.status,
            format_date(volume.created_at),
        ]
        if verbose:
            renderables.append(volume.status_message or "")
        table.add_row(*renderables)
    return table
