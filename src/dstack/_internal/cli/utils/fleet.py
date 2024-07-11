from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.fleets import Fleet
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.utils.common import pretty_date


def print_fleets_table(fleets: List[Fleet], verbose: bool = False) -> None:
    console.print(get_fleets_table(fleets, verbose=verbose))
    console.print()


def get_fleets_table(fleets: List[Fleet], verbose: bool = False) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("INSTANCE")
    table.add_column("BACKEND")
    table.add_column("REGION")
    table.add_column("RESOURCES")
    table.add_column("SPOT")
    table.add_column("PRICE")
    table.add_column("STATUS")
    table.add_column("CREATED")

    for fleet in fleets:
        for i, instance in enumerate(fleet.instances):
            resources = ""
            spot = ""
            if instance.instance_type is not None:
                resources = instance.instance_type.resources.pretty_format()
                spot = "yes" if instance.instance_type.resources.spot else "no"

            status = instance.status.value
            if (
                instance.status in [InstanceStatus.IDLE, InstanceStatus.BUSY]
                and instance.unreachable
            ):
                status += "\n(unreachable)"

            row = [
                fleet.name if i == 0 else "",
                instance.name,
                (instance.backend or "").replace("remote", "ssh"),
                instance.region or "",
                resources,
                spot,
                f"${instance.price:.4}" if instance.price is not None else "",
                status,
                pretty_date(instance.created),
            ]
            table.add_row(*row)

    return table
