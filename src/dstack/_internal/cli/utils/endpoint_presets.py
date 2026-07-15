from collections import defaultdict

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.endpoint_presets import (
    EndpointPreset,
    EndpointPresetValidation,
)
from dstack._internal.utils.common import pretty_resources


def print_endpoint_presets(presets: list[EndpointPreset], verbose: bool = False) -> None:
    table = Table(box=None)
    table.add_column("MODEL", no_wrap=True)
    table.add_column("RESOURCES" if verbose else "GPU")
    table.add_column("CONTEXT", justify="right")
    table.add_column("BENCHMARK", min_width=len("concurrency=1"), overflow="fold")
    presets_by_base: dict[str, list[EndpointPreset]] = defaultdict(list)
    for preset in presets:
        presets_by_base[preset.base].append(preset)

    for base, base_presets in presets_by_base.items():
        add_row_from_dict(table, {"MODEL": f"[bold]{base}[/]"})
        for preset in base_presets:
            _add_preset(table, preset, verbose=verbose)
    console.print(table)
    console.print()


def _add_preset(table: Table, preset: EndpointPreset, *, verbose: bool) -> None:
    groups = preset.service.replica_groups
    column = "RESOURCES" if verbose else "GPU"
    add_row_from_dict(
        table,
        {
            "MODEL": f"[secondary]   preset={preset.id}[/]",
            column: _format_resources(groups[0].resources, verbose=verbose),
            "CONTEXT": format_endpoint_context_length(preset),
            "BENCHMARK": format_endpoint_benchmark(preset, verbose=verbose),
        },
    )
    if preset.model != preset.base:
        add_row_from_dict(
            table,
            {"MODEL": f"   repo={preset.model}"},
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


def format_endpoint_context_length(preset: EndpointPreset) -> str:
    return _format_token_count(preset.context_length)


def format_endpoint_benchmark(preset: EndpointPreset, *, verbose: bool = False) -> str:
    validation = preset.validations[0]
    benchmark = validation.benchmark
    workload = benchmark.workload
    metrics = benchmark.metrics
    requests_per_second = metrics.successful_requests / metrics.duration_seconds
    output_tokens_per_second = metrics.total_output_tokens / metrics.duration_seconds
    parts = [
        f"concurrency={workload.concurrency}",
        f"{_format_number(output_tokens_per_second)} tok/s",
        f"TTFT {_format_latency(metrics.ttft_ms.p50)}",
    ]
    if verbose:
        ttft = _format_latency_summary(
            metrics.ttft_ms.mean, metrics.ttft_ms.p50, metrics.ttft_ms.p99
        )
        tpot = _format_latency_summary(
            metrics.tpot_ms.mean, metrics.tpot_ms.p50, metrics.tpot_ms.p99
        )
        parts.extend(
            [
                f"hardware={_format_validation_gpus(validation)}",
                f"api={workload.api}",
                f"n={workload.num_requests}",
                f"{_format_token_count(workload.input_tokens)}"
                f"->{_format_token_count(workload.output_tokens)}",
                f"{_format_number(requests_per_second)} req/s",
                f"duration={_format_number(metrics.duration_seconds)}s",
                f"TTFT mean/p50/p99={ttft}",
                f"TPOT mean/p50/p99={tpot}",
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


def _format_latency(value_ms: float) -> str:
    if value_ms >= 1000:
        return f"{_format_number(value_ms / 1000)}s"
    return f"{_format_number(value_ms)}ms"


def _format_latency_summary(*values_ms: float) -> str:
    divisor, unit = (1000, "s") if max(values_ms) >= 1000 else (1, "ms")
    return "/".join(_format_number(value / divisor) for value in values_ms) + unit


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
