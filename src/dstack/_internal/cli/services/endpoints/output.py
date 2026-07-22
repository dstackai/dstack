from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from rich.table import Table

from dstack._internal.cli.models.endpoint_presets import (
    EndpointPreset,
)
from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.utils.common import pretty_date, pretty_resources

_STATUS_DISPLAY = {
    "ready": ("verified", "grey"),
    "running": ("clauding", "bold sea_green3"),
    "verifying": ("verifying", "bold deep_sky_blue1"),
    "interrupted": ("interrupted", "bold gold1"),
    "failed": ("failed", "indian_red1"),
}


def _format_status(status: str) -> str:
    text, style = _STATUS_DISPLAY.get(status, (status, None))
    return f"[{style}]{text}[/]" if style else text


def _trials_exhausted(session: dict[str, Any]) -> bool:
    trials = session.get("trials")
    max_trials = session.get("max_trials")
    return (
        isinstance(trials, dict)
        and isinstance(max_trials, int)
        and isinstance(trials.get("count"), int)
        and trials["count"] >= max_trials
    )


def _format_trial_progress(session: Optional[dict[str, Any]]) -> str:
    """The ` (N/M)` suffix; stays outside the status markup to render in the
    default color."""
    if not isinstance(session, dict):
        return ""
    trials = session.get("trials")
    max_trials = session.get("max_trials")
    if not isinstance(trials, dict) or not (trials.get("count") or isinstance(max_trials, int)):
        return ""
    progress = str(trials.get("count") or 0)
    if isinstance(max_trials, int):
        progress += f"/{max_trials}"
    return f" [secondary]({progress})[/]"


def print_endpoint_presets(
    presets: list[EndpointPreset],
    sessions: Optional[list[dict[str, Any]]] = None,
    verbose: bool = False,
) -> None:
    table = Table(box=None)
    table.add_column("BASE", no_wrap=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("RESOURCES" if verbose else "GPU", style="secondary")
    table.add_column("BENCHMARK", min_width=len("con=1"), overflow="fold")
    table.add_column("STATUS", no_wrap=True)
    table.add_column("SUBMITTED", no_wrap=True, style="secondary")
    table.add_column("NAME", no_wrap=True, style="secondary")
    presets_by_base: dict[str, list[EndpointPreset]] = defaultdict(list)
    repo_to_base: dict[str, str] = {}
    for preset in presets:
        presets_by_base[preset.base].append(preset)
        repo_to_base[preset.model] = preset.base
    sessions_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    creations_by_id: dict[str, dict[str, Any]] = {}
    for session in sessions or []:
        if str(session.get("status")) == "success":
            # A completed creation session decorates its preset row.
            creations_by_id[str(session.get("id"))] = session
            continue
        model = str(session.get("model") or "unknown")
        sessions_by_model[repo_to_base.get(model, model)].append(session)

    for base in sorted({*presets_by_base, *sessions_by_model}, key=str.lower):
        add_row_from_dict(table, {"BASE": base})
        # Newest first within a group, as in `dstack ps`.
        for preset in sorted(
            presets_by_base.get(base, []), key=lambda p: p.created_at, reverse=True
        ):
            _add_preset(table, preset, verbose=verbose, creation=creations_by_id.get(preset.id))
        for session in sorted(
            sessions_by_model.get(base, []),
            key=lambda s: str(s.get("created_at") or ""),
            reverse=True,
        ):
            _add_session(table, session)
    console.print(table)
    console.print()


def _add_session(table: Table, session: dict[str, Any], base_label: Optional[str] = None) -> None:
    created = ""
    created_at = session.get("created_at")
    if isinstance(created_at, str):
        try:
            created = pretty_date(datetime.fromisoformat(created_at))
        except ValueError:
            created = created_at
    benchmark = ""
    gpu = ""
    status_key = str(session.get("status", ""))
    if status_key == "running" and _trials_exhausted(session):
        # The trial budget is spent, so the agent is deploying and verifying
        # the final service.
        status_key = "verifying"
    status = _format_status(status_key) + _format_trial_progress(session)
    trials = session.get("trials")
    if isinstance(trials, dict):
        best = trials.get("best")
        if isinstance(best, dict):
            parts = ["best trial:"]
            if best.get("concurrency"):
                parts.append(f"con={best['concurrency']}")
            parts.append(f"{_format_number(best['tok_s'])} tok/s")
            benchmark = " ".join(parts)
            gpu = best.get("gpu") or ""
    add_row_from_dict(
        table,
        {
            "ID": str(session.get("id", "")),
            "NAME": str(session.get("name") or ""),
            "GPU": gpu,
            "RESOURCES": gpu,
            "BENCHMARK": benchmark,
            "STATUS": status,
            "SUBMITTED": created,
        },
    )


def _add_preset(
    table: Table,
    preset: EndpointPreset,
    *,
    verbose: bool,
    creation: Optional[dict[str, Any]] = None,
) -> None:
    groups = preset.service.replica_groups
    column = "RESOURCES" if verbose else "GPU"
    row = {
        "ID": preset.id,
        "NAME": preset.name or "",
        column: _format_resources(groups[0].resources, verbose=verbose),
        "STATUS": _format_status("ready") + _format_trial_progress(creation),
        "BENCHMARK": format_endpoint_benchmark(preset, verbose=verbose),
        "SUBMITTED": pretty_date(preset.created_at),
    }
    if verbose and preset.model != preset.base:
        row["BASE"] = f"[secondary]  repo={preset.model}[/]"
    add_row_from_dict(table, row)
    if len(groups) > 1:
        for group in groups:
            add_row_from_dict(
                table,
                {
                    "BASE": f"  group={group.name}",
                    column: _format_resources(group.resources, verbose=verbose),
                },
                style="secondary",
            )


def format_endpoint_benchmark(preset: EndpointPreset, *, verbose: bool = False) -> str:
    benchmark = preset.validations[0].benchmark
    workload = benchmark.workload
    metrics = benchmark.metrics
    output_tokens_per_second = metrics.total_output_tokens / metrics.duration_seconds
    parts = [
        f"con={workload.concurrency}",
        f"{_format_number(output_tokens_per_second)} tok/s",
        f"TTFT {_format_latency(metrics.ttft_ms.p50)}",
    ]
    if verbose:
        parts.insert(0, f"ctx={_format_token_count(preset.context_length)}")
    return " ".join(parts)


def _format_token_count(value: int) -> str:
    for divisor, suffix in ((1024 * 1024, "M"), (1024, "K")):
        if value >= divisor and value % divisor == 0:
            return f"{value // divisor}{suffix}"
    return str(value)


def _format_number(value: float) -> str:
    # `g` switches to scientific notation for values >= 1000 (after rounding).
    if abs(value) >= 999.5:
        return f"{value:.0f}"
    return f"{value:.3g}"


def _format_latency(value_ms: float) -> str:
    if value_ms >= 1000:
        return f"{_format_number(value_ms / 1000)}s"
    return f"{_format_number(value_ms)}ms"


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
