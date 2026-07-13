from collections import defaultdict

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.endpoint_presets import EndpointPresetRecipe
from dstack._internal.utils.common import pretty_resources


def print_endpoint_presets(recipes: list[EndpointPresetRecipe], verbose: bool = False) -> None:
    table = Table(box=None)
    table.add_column("MODEL", no_wrap=True)
    table.add_column("RESOURCES" if verbose else "GPU")
    recipes_by_base: dict[str, list[EndpointPresetRecipe]] = defaultdict(list)
    for recipe in recipes:
        recipes_by_base[recipe.base].append(recipe)

    for base, base_recipes in recipes_by_base.items():
        add_row_from_dict(table, {"MODEL": f"[bold]{base}[/]"})
        for recipe in base_recipes:
            _add_recipe(table, recipe, verbose=verbose)
    console.print(table)
    console.print()


def _add_recipe(table: Table, recipe: EndpointPresetRecipe, *, verbose: bool) -> None:
    groups = recipe.service.replica_groups
    column = "RESOURCES" if verbose else "GPU"
    add_row_from_dict(
        table,
        {
            "MODEL": f"[secondary]   recipe={recipe.id}[/]",
            column: _format_resources(groups[0].resources, verbose=verbose),
        },
    )
    if recipe.model != recipe.base:
        add_row_from_dict(
            table,
            {"MODEL": f"   repo={recipe.model}"},
            style="secondary",
        )
    if len(groups) > 1:
        for group in groups:
            add_row_from_dict(
                table,
                {
                    "MODEL": f"   group={group.name}",
                    column: _format_resources(group.resources, verbose=verbose),
                },
                style="secondary",
            )
    if verbose:
        add_row_from_dict(
            table,
            {"MODEL": f"   context_length={recipe.context_length}"},
            style="secondary",
        )


def _format_resources(resources, *, verbose: bool) -> str:
    if resources is None:
        return "-"
    if verbose:
        return resources.pretty_format()
    gpu = resources.gpu
    if gpu is None or gpu.count.max == 0:
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
