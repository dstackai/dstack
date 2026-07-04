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
        total_replicas = sum(len(group.tested_resources) for group in preset.replica_spec_groups)
        if total_replicas == 1:
            add_row_from_dict(
                table,
                {
                    "NAME": preset.name,
                    "MODEL": preset.model,
                    "RESOURCES": _format_replica_resources(
                        preset.replica_spec_groups[0].tested_resources[0]
                    ),
                },
            )
            continue
        add_row_from_dict(table, {"NAME": preset.name, "MODEL": preset.model})
        show_group = len(preset.replica_spec_groups) > 1
        last_group_index = None
        for group_index, group in enumerate(preset.replica_spec_groups):
            for replica_num, replica_spec in enumerate(group.tested_resources):
                add_row_from_dict(
                    table,
                    {
                        "NAME": _format_replica_name(
                            group_index=group_index,
                            group_name=group.name,
                            replica_num=replica_num,
                            show_group=show_group,
                            last_group_index=last_group_index,
                        ),
                        "RESOURCES": _format_replica_resources(replica_spec),
                    },
                )
                last_group_index = group_index
    return table


def _format_replica_name(
    *,
    group_index: int,
    group_name: str,
    replica_num: int,
    show_group: bool,
    last_group_index: int | None,
) -> str:
    if not show_group:
        return f"   replica={replica_num}"
    if group_index != last_group_index:
        return f"   group={group_name} replica={replica_num}"
    padding_width = 3 + len(f"group={group_name}") + 1
    return f"{' ' * padding_width}replica={replica_num}"


def _format_replica_resources(resources) -> str:
    formatted = resources.pretty_format()
    if resources.gpu is not None and resources.gpu.count.min == 0 and resources.gpu.count.max == 0:
        return formatted.replace(" gpu=0", "").replace("gpu=0", "-")
    return formatted
