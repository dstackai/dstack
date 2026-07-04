from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.endpoint_presets import EndpointPreset
from dstack._internal.core.models.resources import ResourcesSpec


def print_endpoint_presets_table(presets: List[EndpointPreset]):
    table = get_endpoint_presets_table(presets)
    console.print(table)
    console.print()


def get_endpoint_presets_table(presets: List[EndpointPreset]) -> Table:
    table = Table(box=None)
    table.add_column("NAME", style="bold", no_wrap=True)
    table.add_column("MODEL")
    table.add_column("RESOURCES")

    for preset in presets:
        add_row_from_dict(
            table,
            {
                "NAME": preset.name,
                "MODEL": preset.model,
                "RESOURCES": _format_replica_spec_groups(preset),
            },
        )
    return table


def _format_replica_spec_groups(preset: EndpointPreset) -> str:
    groups = []
    show_group_names = len(preset.replica_spec_groups) > 1
    for group in preset.replica_spec_groups:
        value = _format_replica_specs(group.replica_specs)
        if show_group_names or group.name != "0":
            value = f"{group.name}: {value}"
        groups.append(value)
    return "; ".join(groups) if groups else "-"


def _format_replica_specs(replica_specs: list[ResourcesSpec]) -> str:
    formatted_specs = [spec.pretty_format() for spec in replica_specs]
    if not formatted_specs:
        return "-"
    unique_specs = set(formatted_specs)
    if len(unique_specs) == 1 and len(formatted_specs) > 1:
        return f"{len(formatted_specs)}x {formatted_specs[0]}"
    return ", ".join(formatted_specs)
