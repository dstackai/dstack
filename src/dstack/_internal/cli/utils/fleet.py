from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import Fleet, FleetStatus
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.utils.common import DateFormatter, pretty_date


def print_fleets_table(fleets: List[Fleet], verbose: bool = False) -> None:
    console.print(get_fleets_table(fleets, verbose=verbose))
    console.print()


def get_fleets_table(
    fleets: List[Fleet], verbose: bool = False, format_date: DateFormatter = pretty_date
) -> Table:
    table = Table(box=None)
    table.add_column("FLEET", no_wrap=True)
    if verbose:
        table.add_column("RESERVATION")
    table.add_column("INSTANCE")
    table.add_column("BACKEND")
    if verbose:
        table.add_column("REGION")
    table.add_column("RESOURCES")
    table.add_column("PRICE")
    table.add_column("STATUS")
    table.add_column("CREATED")

    if verbose:
        table.add_column("ERROR")

    for fleet in fleets:
        for i, instance in enumerate(fleet.instances):
            resources = ""
            if instance.instance_type is not None and (
                instance.backend != BackendType.REMOTE
                or instance.status not in [InstanceStatus.PENDING, InstanceStatus.PROVISIONING]
            ):
                resources = instance.instance_type.resources.pretty_format(include_spot=True)

            status = instance.status.value
            total_blocks = instance.total_blocks
            busy_blocks = instance.busy_blocks
            if (
                instance.status in [InstanceStatus.IDLE, InstanceStatus.BUSY]
                and total_blocks is not None
                and total_blocks > 1
            ):
                status = f"{busy_blocks}/{total_blocks} {InstanceStatus.BUSY.value}"
            if (
                instance.status in [InstanceStatus.IDLE, InstanceStatus.BUSY]
                and instance.unreachable
            ):
                status += "\n(unreachable)"

            backend = instance.backend or ""
            if backend == "remote":
                backend = "ssh"

            region = ""
            if instance.region:
                region = f"{instance.region}"
                if verbose:
                    if instance.availability_zone:
                        region += f" ({instance.availability_zone})"
                else:
                    backend += f" ({instance.region})"
            error = ""
            if instance.status == InstanceStatus.TERMINATED and instance.termination_reason:
                error = f"{instance.termination_reason}"
            row = {
                "FLEET": fleet.name if i == 0 else "",
                "RESERVATION": fleet.spec.configuration.reservation or "" if i == 0 else "",
                "INSTANCE": str(instance.instance_num),
                "BACKEND": backend,
                "REGION": region,
                "RESOURCES": resources,
                "PRICE": f"${instance.price:.4f}".rstrip("0").rstrip(".")
                if instance.price is not None
                else "",
                "STATUS": status,
                "CREATED": format_date(instance.created),
                "ERROR": error,
            }
            add_row_from_dict(table, row)

        if len(fleet.instances) == 0 and fleet.status != FleetStatus.TERMINATING:
            row = {
                "FLEET": fleet.name,
                "RESERVATION": "-",
                "INSTANCE": "-",
                "BACKEND": "-",
                "REGION": "-",
                "RESOURCES": "-",
                "PRICE": "-",
                "STATUS": "-",
                "CREATED": format_date(fleet.created_at),
                "ERROR": "-",
            }
            add_row_from_dict(table, row)

    return table
