from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.endpoint_presets import EndpointPreset


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
        if len(preset.replica_spec_groups) == 1:
            add_row_from_dict(
                table,
                {
                    "NAME": preset.name,
                    "MODEL": preset.model,
                    "RESOURCES": _format_resources(preset.replica_spec_groups[0].resources),
                },
            )
            continue
        add_row_from_dict(table, {"NAME": preset.name, "MODEL": preset.model})
        for group in preset.replica_spec_groups:
            add_row_from_dict(
                table,
                {
                    "NAME": f"   group={group.name}",
                    "RESOURCES": _format_resources(group.resources),
                },
            )
    return table


def _format_resources(resources) -> str:
    formatted = resources.pretty_format()
    if resources.gpu is not None and resources.gpu.count.min == 0:
        if resources.gpu.count.max in (None, 0):
            return (
                formatted.replace(" gpu=0..", "")
                .replace(" gpu=0", "")
                .replace("gpu=0..", "-")
                .replace("gpu=0", "-")
            )
    return formatted
