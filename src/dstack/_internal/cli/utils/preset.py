from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.endpoint_presets import EndpointPreset, EndpointPresetRecipe
from dstack._internal.utils.common import pretty_resources


def print_endpoint_presets_table(presets: List[EndpointPreset], verbose: bool = False):
    table = get_endpoint_presets_table(presets, verbose=verbose)
    console.print(table)
    console.print()


def get_endpoint_presets_table(presets: List[EndpointPreset], verbose: bool = False) -> Table:
    table = Table(box=None)
    table.add_column("MODEL", no_wrap=True)
    if verbose:
        table.add_column("RESOURCES")
    else:
        table.add_column("GPU")

    for preset in presets:
        if len(preset.recipes) == 1:
            _add_recipe_rows(
                table,
                preset_base=preset.base,
                label=f"[bold]{preset.base}[/]",
                recipe=preset.recipes[0],
                verbose=verbose,
            )
            continue
        add_row_from_dict(table, {"MODEL": f"[bold]{preset.base}[/]"})
        for recipe_num, recipe in enumerate(preset.recipes):
            _add_recipe_rows(
                table,
                preset_base=preset.base,
                label=f"[secondary]   recipe={recipe_num}[/]",
                recipe=recipe,
                verbose=verbose,
            )
    return table


def _add_recipe_rows(
    table: Table,
    preset_base: str,
    label: str,
    recipe: EndpointPresetRecipe,
    verbose: bool,
) -> None:
    groups = recipe.service.replica_groups
    column = "RESOURCES" if verbose else "GPU"
    if len(groups) == 1:
        add_row_from_dict(
            table,
            {
                "MODEL": label,
                column: _format_resources(groups[0].resources, verbose=verbose),
            },
        )
        _add_recipe_model_row(
            table,
            preset_base=preset_base,
            recipe_model=recipe.model,
        )
        return

    add_row_from_dict(table, {"MODEL": label})
    _add_recipe_model_row(
        table,
        preset_base=preset_base,
        recipe_model=recipe.model,
    )
    for group in groups:
        add_row_from_dict(
            table,
            {
                "MODEL": f"[secondary]   group={group.name}[/]",
                column: _format_resources(group.resources, verbose=verbose),
            },
        )


def _add_recipe_model_row(
    table: Table,
    preset_base: str,
    recipe_model: str,
) -> None:
    if recipe_model == preset_base:
        return
    add_row_from_dict(table, {"MODEL": f"   repo={recipe_model}"}, style="secondary")


def _format_resources(resources, verbose: bool) -> str:
    if not verbose:
        if resources.gpu is None:
            return "-"
        return _format_gpu(resources)
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


def _format_gpu(resources) -> str:
    gpu = resources.gpu
    assert gpu is not None
    if gpu.count.min == 0 and gpu.count.max in (None, 0):
        return "-"
    formatted = pretty_resources(
        gpu_vendor=gpu.vendor,
        gpu_name=",".join(gpu.name) if gpu.name else None,
        gpu_count=gpu.count,
        gpu_memory=gpu.memory,
        total_gpu_memory=gpu.total_memory,
        compute_capability=gpu.compute_capability,
    )
    return formatted.removeprefix("gpu=") or "-"
