from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
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
    if verbose:
        table.add_column("ATTACHED")
    table.add_column("CREATED")
    if verbose:
        table.add_column("ERROR")

    for volume in volumes:
        backend = f"{volume.configuration.backend.value} ({volume.configuration.region})"
        region = volume.configuration.region
        if verbose:
            backend = volume.configuration.backend.value
            if (
                verbose
                and volume.provisioning_data is not None
                and volume.provisioning_data.availability_zone is not None
            ):
                region += f" ({volume.provisioning_data.availability_zone})"
        attached = "-"
        if volume.attachments is not None:
            attached = ", ".join(
                {va.instance.fleet_name for va in volume.attachments if va.instance.fleet_name}
            )
            attached = attached or "-"
        row = {
            "NAME": volume.name,
            "BACKEND": backend,
            "REGION": region,
            "STATUS": volume.status,
            "ATTACHED": attached,
            "CREATED": format_date(volume.created_at),
            "ERROR": volume.status_message,
        }
        add_row_from_dict(table, row)
    return table
