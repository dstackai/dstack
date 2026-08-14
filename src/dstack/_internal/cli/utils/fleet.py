from typing import Any, List, Optional

from rich.table import Table

from dstack._internal.cli.utils.common import (
    add_row_from_dict,
    console,
    format_backend,
    format_entity_reference,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import Fleet, FleetNodesSpec, FleetStatus
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import Instance, InstanceStatus
from dstack._internal.core.models.resources import GPUSpec, ResourcesSpec
from dstack._internal.utils.common import DateFormatter, pretty_date

# Status styles. Bold marks transient states and states that need attention.
# NOTE: "grey" is not a valid rich color — rich silently drops the whole style. Use "grey58".
_FLEET_STATUS_STYLES = {
    FleetStatus.SUBMITTED: "grey58",
    FleetStatus.ACTIVE: "grey58",
    FleetStatus.TERMINATING: "bold deep_sky_blue1",
    FleetStatus.TERMINATED: "grey58",
    FleetStatus.FAILED: "bold indian_red1",
}
_INSTANCE_STATUS_STYLES = {
    InstanceStatus.PENDING: "bold deep_sky_blue1",
    InstanceStatus.PROVISIONING: "bold deep_sky_blue1",
    InstanceStatus.IDLE: "bold sea_green3",
    InstanceStatus.BUSY: "bold deep_sky_blue1",
    InstanceStatus.TERMINATING: "bold deep_sky_blue1",
    InstanceStatus.TERMINATED: "grey58",
}


def _dim(value: str) -> str:
    """Renders a value as secondary, leaving blanks alone so they produce no markup."""
    return f"[secondary]{value}[/]" if value else ""


def print_fleets_table(fleets: List[Fleet], current_project: str, verbose: bool = False) -> None:
    console.print(get_fleets_table(fleets, current_project=current_project, verbose=verbose))
    console.print()


def get_fleets_table(
    fleets: List[Fleet],
    current_project: str,
    verbose: bool = False,
    format_date: DateFormatter = pretty_date,
) -> Table:
    table = Table(box=None)

    # Columns. A fleet row describes what was requested and is dimmed; an instance row shows
    # what exists and stays bright, so the per-row-type columns are dimmed below instead.
    # Bold is reserved for statuses that need attention.
    table.add_column("NAME", no_wrap=True)
    table.add_column("NODES", style="grey58")
    if verbose:
        table.add_column("RESOURCES")
        table.add_column("DRIVER")
    else:
        table.add_column("GPU")
    table.add_column("SPOT", style="grey58")
    table.add_column("BACKEND")
    table.add_column("PRICE")
    table.add_column("STATUS", no_wrap=True)
    table.add_column("CREATED", style="grey58", no_wrap=True)
    if verbose:
        table.add_column("ERROR")

    # Most recently created fleets first. The `/fleets/list` endpoint returns them unordered.
    fleets = sorted(fleets, key=lambda f: f.created_at, reverse=True)

    for fleet in fleets:
        # Fleet row
        config = fleet.spec.configuration
        merged_profile = fleet.spec.merged_profile

        # Detect SSH fleet vs backend fleet
        if config.ssh_config is not None:
            # SSH fleet: fixed number of hosts, no cloud billing
            nodes = str(len(config.ssh_config.hosts))
            resources = ""
            gpu = ""
            backend = "ssh"
            spot_policy = ""
            max_price = ""
        else:
            # Backend fleet: dynamic nodes, cloud billing
            nodes = _format_nodes(config.nodes)
            resources = config.resources.pretty_format() if config.resources else ""
            gpu = _format_fleet_gpu(config.resources)
            backend = _format_backends(config.backends)
            spot_policy = ""
            if merged_profile and merged_profile.spot_policy:
                spot_policy = merged_profile.spot_policy.value
            # Format as "$0..X.XX" range, or blank if not set
            if merged_profile and merged_profile.max_price is not None:
                max_price = f"$0..{_format_amount(merged_profile.max_price)}"
            else:
                max_price = ""

        # In verbose mode, append placement to nodes if cluster
        if verbose and config.placement and config.placement.value == "cluster":
            nodes = f"{nodes} (cluster)"

        fleet_name = format_entity_reference(fleet.name, fleet.project_name, current_project)
        # The whole fleet row is dimmed: it describes what was requested, not what exists
        fleet_row = {
            "NAME": _dim(fleet_name),
            "NODES": nodes,
            "RESOURCES": _dim(resources),
            "GPU": _dim(gpu),
            "BACKEND": _dim(backend),
            "PRICE": _dim(max_price),
            "SPOT": spot_policy,
            "STATUS": _format_fleet_status(fleet),
            "CREATED": format_date(fleet.created_at),
        }

        add_row_from_dict(table, fleet_row)

        # Instance rows (indented)
        for instance in fleet.instances:
            # Check if this is an SSH instance
            is_ssh_instance = instance.backend == BackendType.REMOTE

            # Format backend with region (and AZ in verbose mode)
            if verbose and instance.availability_zone:
                # In verbose mode, show AZ instead of region (AZ is more specific)
                backend_with_region = _format_instance_backend(
                    instance.backend, instance.availability_zone
                )
            else:
                backend_with_region = _format_instance_backend(instance.backend, instance.region)

            # Get spot info from instance resources (not applicable to SSH)
            if is_ssh_instance:
                instance_spot = ""
                instance_price = ""
            else:
                instance_spot = ""
                if (
                    instance.instance_type is not None
                    and instance.instance_type.resources is not None
                ):
                    instance_spot = (
                        "spot" if instance.instance_type.resources.spot else "on-demand"
                    )
                instance_price = _format_price(instance.price)

            instance_row = {
                "NAME": f"   instance={instance.instance_num}",
                "NODES": "",
                "RESOURCES": _format_instance_resources(instance),
                "GPU": _format_instance_gpu(instance),
                "BACKEND": backend_with_region,
                "DRIVER": instance.gpu_driver.version if instance.gpu_driver else "",
                "PRICE": instance_price,
                "SPOT": instance_spot,
                "STATUS": _format_instance_status(instance),
                "CREATED": format_date(instance.created),
            }

            if instance.status == InstanceStatus.TERMINATED and instance.termination_reason:
                instance_row["ERROR"] = instance.termination_reason

            # No row-level dimming: only the columns styled above are dimmed on instance rows
            add_row_from_dict(table, instance_row)

    return table


def _format_nodes(nodes: Optional[FleetNodesSpec]) -> str:
    """Format nodes spec as '0..1', '3', '2..10', etc."""
    if nodes is None:
        return ""
    if nodes.min == nodes.max:
        return str(nodes.min)
    if nodes.max is None:
        return f"{nodes.min}.."
    return f"{nodes.min}..{nodes.max}"


def _format_instance_backend(backend: Optional[BackendType], region: Optional[str]) -> str:
    """Both the backend and its region are real values, so only the parentheses are dimmed."""
    if backend is None or not region:
        return format_backend(backend, region)
    return f"{format_backend(backend, None)} [secondary]([/]{region}[secondary])[/]"


def _format_backends(backends: Optional[List[BackendType]]) -> str:
    if backends is None or len(backends) == 0:
        return "*"
    return ", ".join(b.value.replace("remote", "ssh") for b in backends)


def _format_range(min_val: Optional[Any], max_val: Optional[Any]) -> str:
    if min_val is None and max_val is None:
        return ""
    if min_val == max_val:
        return str(min_val)
    if max_val is None:
        return f"{min_val}.."
    if min_val is None:
        return f"..{max_val}"
    return f"{min_val}..{max_val}"


def _format_fleet_gpu(resources: Optional[ResourcesSpec]) -> str:
    """Extract GPU-only info from fleet requirements, handling ranges."""
    if resources is None or resources.gpu is None:
        return ""

    gpu: GPUSpec = resources.gpu

    # Check if there's actually a GPU requirement
    count = gpu.count
    if count is None or (count.min == 0 and (count.max is None or count.max == 0)):
        return ""

    parts = []

    # GPU name(s)
    if gpu.name:
        parts.append(",".join(gpu.name))
    else:
        parts.append("gpu")

    # GPU memory (range)
    if gpu.memory is not None:
        mem_str = _format_range(gpu.memory.min, gpu.memory.max)
        if mem_str:
            parts.append(mem_str)

    # GPU count (range)
    count_str = _format_range(count.min, count.max)
    if count_str:
        parts.append(count_str)

    return ":".join(parts)


def _format_fleet_status(fleet: Fleet) -> str:
    style = _FLEET_STATUS_STYLES.get(fleet.status, "white")
    return f"[{style}]{fleet.status.value}[/]"


def _format_instance_status(instance: Instance) -> str:
    """Format instance status with colors and health info."""
    status = instance.status
    style = _INSTANCE_STATUS_STYLES.get(status, "white")

    total_blocks = instance.total_blocks
    if status.is_available() and total_blocks is not None and total_blocks > 1:
        # Reads as "<busy_blocks> of <total_blocks> busy": the fraction is a quantity, so it's
        # dimmed, while the word keeps the color of the status (no busy blocks is still idle).
        status_text = (
            f"[secondary]{instance.busy_blocks}/{total_blocks}[/]"
            f" [{style}]{InstanceStatus.BUSY.value}[/]"
        )
    else:
        status_text = f"[{style}]{status.value}[/]"

    if status.is_available():
        if instance.unreachable:
            status_text += " [bold indian_red1](unreachable)[/]"
        elif instance.health_status == HealthStatus.WARNING:
            status_text += " [bold gold1](warning)[/]"
        elif not instance.health_status.is_healthy():
            status_text += f" [bold indian_red1]({instance.health_status.value})[/]"

    return status_text


def _format_amount(price: float) -> str:
    """Formats a price without a currency sign, trimming trailing zeros."""
    return f"{price:.4f}".rstrip("0").rstrip(".")


def _format_price(price: Optional[float]) -> str:
    if price is None:
        return ""
    return f"${_format_amount(price)}"


def _format_instance_gpu(instance: Instance) -> str:
    if instance.instance_type is None:
        return ""
    if instance.backend == BackendType.REMOTE and instance.status in [
        InstanceStatus.PENDING,
        InstanceStatus.PROVISIONING,
    ]:
        return ""
    return instance.instance_type.resources.pretty_format(gpu_only=True, include_spot=False)


def _format_instance_resources(instance: Instance) -> str:
    if instance.instance_type is None:
        return ""
    if instance.backend == BackendType.REMOTE and instance.status in [
        InstanceStatus.PENDING,
        InstanceStatus.PROVISIONING,
    ]:
        return ""
    return instance.instance_type.resources.pretty_format(include_spot=False)
