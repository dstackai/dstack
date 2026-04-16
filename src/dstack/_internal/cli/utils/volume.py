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
        backend = volume.get_backend().value
        region = volume.get_region()
        if verbose:
            # In verbose mode, BACKEND displays `backend` only, and REGION displays nothing or
            # `region` or `region (az)`
            if availability_zone := volume.get_availability_zone():
                region = f"{region} ({availability_zone})"
        elif region:
            # In non-verbose mode, BACKEND displays `backend` or `backend (region)`, and REGION
            # is hidden
            backend = f"{backend} ({region})"
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
