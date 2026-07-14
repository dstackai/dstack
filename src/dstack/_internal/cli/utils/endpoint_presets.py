from collections import defaultdict

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.endpoint_presets import (
    EndpointBenchmark,
    EndpointPresetRecipe,
    EndpointPresetValidation,
)
from dstack._internal.utils.common import pretty_resources


def print_endpoint_presets(recipes: list[EndpointPresetRecipe], verbose: bool = False) -> None:
    table = Table(box=None)
    table.add_column("MODEL", no_wrap=True)
    table.add_column("RESOURCES" if verbose else "GPU")
    table.add_column("CONTEXT", justify="right")
    table.add_column("BENCHMARK")
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
    validation = recipe.validations[0]
    benchmark = validation.benchmark
    add_row_from_dict(
        table,
        {
            "MODEL": f"[secondary]   recipe={recipe.id}[/]",
            column: _format_resources(groups[0].resources, verbose=verbose),
            "CONTEXT": _format_token_count(recipe.context_length),
            "BENCHMARK": _format_benchmark(validation, benchmark, verbose=verbose),
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


def _format_benchmark(
    validation: EndpointPresetValidation,
    benchmark: EndpointBenchmark,
    *,
    verbose: bool,
) -> str:
    workload = benchmark.workload
    metrics = benchmark.metrics
    requests_per_second = metrics.successful_requests / metrics.duration_seconds
    output_tokens_per_second = metrics.total_output_tokens / metrics.duration_seconds
    parts = [
        f"{_format_number(output_tokens_per_second)} tok/s",
        f"TTFT {_format_number(metrics.ttft_ms.p50)}ms",
    ]
    if verbose:
        parts.extend(
            [
                f"hardware={_format_validation_gpus(validation)}",
                f"api={workload.api}",
                f"n={workload.num_requests}",
                f"c={workload.concurrency}",
                f"{_format_token_count(workload.input_tokens)}"
                f"->{_format_token_count(workload.output_tokens)}",
                f"{_format_number(requests_per_second)} req/s",
                f"duration={_format_number(metrics.duration_seconds)}s",
                "TTFT mean/p50/p99="
                f"{_format_number(metrics.ttft_ms.mean)}/"
                f"{_format_number(metrics.ttft_ms.p50)}/"
                f"{_format_number(metrics.ttft_ms.p99)}ms",
                "TPOT mean/p50/p99="
                f"{_format_number(metrics.tpot_ms.mean)}/"
                f"{_format_number(metrics.tpot_ms.p50)}/"
                f"{_format_number(metrics.tpot_ms.p99)}ms",
                f"{benchmark.tool} {benchmark.tool_version}",
            ]
        )
    return " ".join(parts)


def _format_validation_gpus(validation: EndpointPresetValidation) -> str:
    gpus = [
        _format_resources(resources, verbose=False)
        for replica_group in validation.replicas
        for resources in replica_group.resources
    ]
    return "+".join(gpus) or "-"


def _format_token_count(value: int) -> str:
    for divisor, suffix in ((1024 * 1024, "M"), (1024, "K")):
        if value >= divisor and value % divisor == 0:
            return f"{value // divisor}{suffix}"
    return str(value)


def _format_number(value: float) -> str:
    return f"{value:.3g}"


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
