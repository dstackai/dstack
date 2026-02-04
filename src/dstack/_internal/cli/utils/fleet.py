from typing import Any, Dict, List, Optional, Union

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import Fleet, FleetNodesSpec, FleetStatus
from dstack._internal.core.models.instances import Instance, InstanceStatus
from dstack._internal.core.models.resources import GPUSpec, ResourcesSpec
from dstack._internal.utils.common import DateFormatter, pretty_date


def print_fleets_table(fleets: List[Fleet], verbose: bool = False) -> None:
    console.print(get_fleets_table(fleets, verbose=verbose))
    console.print()


def get_fleets_table(
    fleets: List[Fleet], verbose: bool = False, format_date: DateFormatter = pretty_date
) -> Table:
    table = Table(box=None)

    # Columns
    table.add_column("NAME", style="bold", no_wrap=True)
    table.add_column("NODES")
    if verbose:
        table.add_column("RESOURCES")
    else:
        table.add_column("GPU")
    table.add_column("SPOT")
    table.add_column("BACKEND")
    table.add_column("PRICE")
    table.add_column("STATUS", no_wrap=True)
    table.add_column("CREATED", no_wrap=True)
    if verbose:
        table.add_column("ERROR")

    for fleet in fleets:
        # Fleet row
        config = fleet.spec.configuration
        merged_profile = fleet.spec.merged_profile

        # Detect SSH fleet vs backend fleet
        if config.ssh_config is not None:
            # SSH fleet: fixed number of hosts, no cloud billing
            nodes = str(len(config.ssh_config.hosts))
            backend = "ssh"
            spot_policy = "-"
            max_price = "-"
        else:
            # Backend fleet: dynamic nodes, cloud billing
            nodes = _format_nodes(config.nodes)
            backend = _format_backends(config.backends)
            spot_policy = "-"
            if merged_profile and merged_profile.spot_policy:
                spot_policy = merged_profile.spot_policy.value
            # Format as "$0..$X.XX" range, or "-" if not set
            if merged_profile and merged_profile.max_price is not None:
                max_price = f"$0..{_format_price(merged_profile.max_price)}"
            else:
                max_price = "-"

        # In verbose mode, append placement to nodes if cluster
        if verbose and config.placement and config.placement.value == "cluster":
            nodes = f"{nodes} (cluster)"

        fleet_row: Dict[Union[str, int], Any] = {
            "NAME": fleet.name,
            "NODES": nodes,
            "BACKEND": backend,
            "PRICE": max_price,
            "SPOT": spot_policy,
            "STATUS": _format_fleet_status(fleet),
            "CREATED": format_date(fleet.created_at),
        }

        if verbose:
            fleet_row["RESOURCES"] = config.resources.pretty_format() if config.resources else "-"
            fleet_row["ERROR"] = ""
        else:
            fleet_row["GPU"] = _format_fleet_gpu(config.resources)

        add_row_from_dict(table, fleet_row)

        # Instance rows (indented)
        for instance in fleet.instances:
            # Check if this is an SSH instance
            is_ssh_instance = instance.backend == BackendType.REMOTE

            # Format backend with region (and AZ in verbose mode)
            if verbose and instance.availability_zone:
                # In verbose mode, show AZ instead of region (AZ is more specific)
                backend_with_region = _format_backend(instance.backend, instance.availability_zone)
            else:
                backend_with_region = _format_backend(instance.backend, instance.region)

            # Get spot info from instance resources (not applicable to SSH)
            if is_ssh_instance:
                instance_spot = "-"
                instance_price = "-"
            else:
                instance_spot = "-"
                if (
                    instance.instance_type is not None
                    and instance.instance_type.resources is not None
                ):
                    instance_spot = (
                        "spot" if instance.instance_type.resources.spot else "on-demand"
                    )
                instance_price = _format_price(instance.price)

            instance_row: Dict[Union[str, int], Any] = {
                "NAME": f"   instance={instance.instance_num}",
                "NODES": "",
                "BACKEND": backend_with_region,
                "PRICE": instance_price,
                "SPOT": instance_spot,
                "STATUS": _format_instance_status(instance),
                "CREATED": format_date(instance.created),
            }

            if verbose:
                instance_row["RESOURCES"] = _format_instance_resources(instance)
                error = ""
                if instance.status == InstanceStatus.TERMINATED and instance.termination_reason:
                    error = instance.termination_reason
                instance_row["ERROR"] = error
            else:
                instance_row["GPU"] = _format_instance_gpu(instance)

            add_row_from_dict(table, instance_row, style="secondary")

    return table


def _format_nodes(nodes: Optional[FleetNodesSpec]) -> str:
    """Format nodes spec as '0..1', '3', '2..10', etc."""
    if nodes is None:
        return "-"
    if nodes.min == nodes.max:
        return str(nodes.min)
    if nodes.max is None:
        return f"{nodes.min}.."
    return f"{nodes.min}..{nodes.max}"


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
        return "-"

    gpu: GPUSpec = resources.gpu

    # Check if there's actually a GPU requirement
    count = gpu.count
    if count is None or (count.min == 0 and (count.max is None or count.max == 0)):
        return "-"

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
    status = fleet.status
    status_text = status.value

    color_map = {
        FleetStatus.SUBMITTED: "grey",
        FleetStatus.ACTIVE: "white",
        FleetStatus.TERMINATING: "deep_sky_blue1",
        FleetStatus.TERMINATED: "grey",
        FleetStatus.FAILED: "indian_red1",
    }
    color = color_map.get(status, "white")
    is_finished = status in [FleetStatus.TERMINATED, FleetStatus.FAILED]
    status_style = f"bold {color}" if not is_finished else color
    return f"[{status_style}]{status_text}[/]"


def _format_instance_status(instance: Instance) -> str:
    """Format instance status with colors and health info."""
    status = instance.status
    status_text = status.value

    total_blocks = instance.total_blocks
    busy_blocks = instance.busy_blocks
    if (
        status in [InstanceStatus.IDLE, InstanceStatus.BUSY]
        and total_blocks is not None
        and total_blocks > 1
    ):
        status_text = f"{busy_blocks}/{total_blocks} {InstanceStatus.BUSY.value}"

    # Add health status
    health_suffix = ""
    if status in [InstanceStatus.IDLE, InstanceStatus.BUSY]:
        if instance.unreachable:
            health_suffix = " (unreachable)"
        elif not instance.health_status.is_healthy():
            health_suffix = f" ({instance.health_status.value})"

    color_map = {
        InstanceStatus.PENDING: "deep_sky_blue1",
        InstanceStatus.PROVISIONING: "deep_sky_blue1",
        InstanceStatus.IDLE: "sea_green3",
        InstanceStatus.BUSY: "white",
        InstanceStatus.TERMINATING: "deep_sky_blue1",
        InstanceStatus.TERMINATED: "grey",
    }
    color = color_map.get(status, "white")
    is_finished = status == InstanceStatus.TERMINATED
    status_style = f"bold {color}" if not is_finished else color
    return f"[{status_style}]{status_text}{health_suffix}[/]"


def _format_backend(backend: Optional[BackendType], region: Optional[str]) -> str:
    if backend is None:
        return "-"
    backend_str = backend.value
    if backend == BackendType.REMOTE:
        backend_str = "ssh"
    if region:
        backend_str += f" ({region})"
    return backend_str


def _format_price(price: Optional[float]) -> str:
    if price is None:
        return "-"
    return f"${price:.4f}".rstrip("0").rstrip(".")


def _format_instance_gpu(instance: Instance) -> str:
    if instance.instance_type is None:
        return "-"
    if instance.backend == BackendType.REMOTE and instance.status in [
        InstanceStatus.PENDING,
        InstanceStatus.PROVISIONING,
    ]:
        return "-"
    return instance.instance_type.resources.pretty_format(gpu_only=True, include_spot=False) or "-"


def _format_instance_resources(instance: Instance) -> str:
    if instance.instance_type is None:
        return "-"
    if instance.backend == BackendType.REMOTE and instance.status in [
        InstanceStatus.PENDING,
        InstanceStatus.PROVISIONING,
    ]:
        return "-"
    return instance.instance_type.resources.pretty_format(include_spot=False)
